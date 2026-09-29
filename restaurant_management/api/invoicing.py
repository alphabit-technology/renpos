# -*- coding: utf-8 -*-
# restaurant_management/api/invoicing.py
#
# Creates the ERPNext invoice for a paid Table Order, compatible with
# ERPNext v15 and v16:
#
#   v15  -> always POS Invoice (consolidated into Sales Invoices by the
#           POS Closing Entry, like ERPNext's own POS).
#   v16  -> honours POS Settings "Invoice Type Created via POS Screen"
#           (field `invoice_type`: "POS Invoice" or "Sales Invoice").
#
# Both modes require the cashier to have an open POS Opening Entry,
# exactly like ERPNext's Point of Sale page.

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

POS_INVOICE = "POS Invoice"
SALES_INVOICE = "Sales Invoice"


def get_invoice_doctype():
    """Which invoice DocType the POS must create on this site."""
    if frappe.get_meta("POS Settings").has_field("invoice_type"):  # v16+
        value = frappe.db.get_single_value("POS Settings", "invoice_type")
        if value in (POS_INVOICE, SALES_INVOICE):
            return value
    return POS_INVOICE


def is_v16_pos():
    """ERPNext v16 POS (POS Settings has invoice_type)."""
    return frappe.get_meta("POS Settings").has_field("invoice_type")


def get_open_opening_entry(pos_profile, user=None):
    """
    The cashier's own open POS Opening Entry (cash register shift) for this
    POS Profile. Each cashier works with their own register: the POS
    Closing Entry only collects invoices owned by the shift's user.
    """
    rows = frappe.get_all(
        "POS Opening Entry",
        filters={
            "user": user or frappe.session.user,
            "pos_profile": pos_profile,
            "docstatus": 1,
            "pos_closing_entry": ["in", ["", None]],
        },
        fields=["name", "company", "user", "period_start_date"],
        order_by="period_start_date desc",
        limit=1,
    )
    return rows[0] if rows else None


def _payment_account(mode_of_payment, company):
    from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account

    return (get_bank_cash_account(mode_of_payment, company) or {}).get("account")


def create_invoice(order, payments):
    """
    Build, insert and submit the invoice for `order`.

    `payments`: list of {"mode_of_payment": str, "amount": number}.
    Returns the submitted invoice document.
    """
    opening = get_open_opening_entry(order.pos_profile)
    if not opening:
        frappe.throw(
            _("Open your cash register (POS Opening Entry) for POS Profile {0} before taking payments.").format(
                frappe.bold(order.pos_profile)
            ),
            title=_("Cash register is closed"),
        )

    # v16 rejects invoices against a shift opened on a previous day.
    if is_v16_pos() and getdate(opening.period_start_date) != getdate(nowdate()):
        frappe.throw(
            _("The cash register shift {0} was opened on {1}. Close it (POS Closing Entry) and open a new one.").format(
                frappe.bold(opening.name), frappe.format_value(opening.period_start_date, {"fieldtype": "Datetime"})
            ),
            title=_("Outdated cash register shift"),
        )

    profile = frappe.get_cached_doc("POS Profile", order.pos_profile)
    allowed_modes = {p.mode_of_payment for p in profile.payments}

    clean_payments = []
    for p in payments or []:
        mode = p.get("mode_of_payment")
        amount = flt(p.get("amount"))
        if amount == 0:
            continue
        if amount < 0:
            frappe.throw(_("Payment amounts must be positive"))
        if mode not in allowed_modes:
            frappe.throw(_("Mode of payment {0} is not enabled in POS Profile {1}").format(mode, profile.name))
        clean_payments.append((mode, amount))

    if not clean_payments:
        frappe.throw(_("At least one payment is required"))

    doctype = get_invoice_doctype()
    inv = frappe.new_doc(doctype)
    inv.update({
        "is_pos": 1,
        "pos_profile": profile.name,
        "company": profile.company,
        "customer": order.customer or profile.customer,
        "posting_date": nowdate(),
        "selling_price_list": profile.selling_price_list,
        "currency": profile.currency,
        "update_stock": profile.update_stock,
        "set_warehouse": profile.warehouse,
        "taxes_and_charges": profile.taxes_and_charges,
    })
    if doctype == SALES_INVOICE and inv.meta.has_field("is_created_using_pos"):  # v16
        inv.is_created_using_pos = 1
    # Prices were already validated per row (api.order); ERPNext must not
    # re-apply pricing rules on top of them.
    inv.ignore_pricing_rule = 1

    order_rows = [i for i in order.entry_items if flt(i.qty) > 0]
    for item in order_rows:
        inv.append("items", {
            "item_code": item.item_code,
            "qty": item.qty,
            "price_list_rate": item.price_list_rate,
            "discount_percentage": item.discount_percentage,
            "rate": item.rate,
            "warehouse": profile.warehouse,
            "batch_no": item.batch_no or None,
            "serial_no": item.serial_no or None,
        })

    if not inv.items:
        frappe.throw(_("The order has no items to invoice"))

    # Pull POS Profile defaults (accounts, cost center, taxes, payment rows…)
    inv.set_missing_values()
    if inv.taxes_and_charges and not inv.get("taxes"):
        inv.set_taxes()

    # set_missing_values() copies ignore_pricing_rule from the POS Profile;
    # force it again (validate won't overwrite it) so ERPNext doesn't re-apply
    # rules or add free-item rows on top of the validated order prices.
    inv.ignore_pricing_rule = 1

    # keep the order's prices on every row
    for row, src in zip(inv.items, order_rows):
        row.price_list_rate = src.price_list_rate
        row.discount_percentage = src.discount_percentage
        row.rate = src.rate
        row.pricing_rules = ""

    inv.set("payments", [])
    for mode, amount in clean_payments:
        inv.append("payments", {
            "mode_of_payment": mode,
            "amount": amount,
            "account": _payment_account(mode, profile.company),
        })

    inv.calculate_taxes_and_totals()

    _check_paid(inv, clean_payments)

    # Access was checked by the caller (restaurant role, order permission,
    # POS Profile and an open cash register).
    inv.flags.ignore_permissions = True
    inv.insert()

    # Totals after ERPNext's own validation are the ones that count.
    if len(inv.items) != len(order_rows):
        frappe.throw(_("The invoice items don't match the order; check pricing rules for free items."))
    _check_paid(inv, clean_payments)

    inv.submit()
    return inv


def _check_paid(inv, clean_payments):
    total_due = flt(inv.rounded_total or inv.grand_total, inv.precision("grand_total"))
    paid = flt(sum(a for _m, a in clean_payments), inv.precision("grand_total"))
    if paid < total_due:
        frappe.throw(
            _("Paid amount {0} is less than the total {1}").format(
                frappe.format_value(paid, {"fieldtype": "Currency", "options": inv.currency}),
                frappe.format_value(total_due, {"fieldtype": "Currency", "options": inv.currency}),
            ),
            title=_("Insufficient payment"),
        )
