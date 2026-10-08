# -*- coding: utf-8 -*-
# renpos/api/invoicing.py
#
# Creates the ERPNext invoice for a paid Ren Order, compatible with
# ERPNext v15 and v16:
#
#   v15  -> always POS Invoice (consolidated into Sales Invoices by the
#           POS Closing Entry, like ERPNext's own POS).
#   v16  -> honours POS Settings "Invoice Type Created via POS Screen"
#           (field `invoice_type`: "POS Invoice" or "Sales Invoice").
#
# Both modes require the cashier to have an open POS Opening Entry,
# exactly like ERPNext's Point of Sale page.

from contextlib import contextmanager

import frappe
from frappe import _
from renpos.api.guards import effective_price_list
from frappe.utils import cint, flt, getdate, nowdate

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


def open_entries(pos_profile=None, user=None):
    """
    Open POS Opening Entries of a POS Profile and/or a user. ERPNext v16 allows
    one open register per POS Profile and one per user, whoever opened it.
    """
    filters = {"docstatus": 1, "status": "Open", "pos_closing_entry": ["in", ["", None]]}
    if pos_profile:
        filters["pos_profile"] = pos_profile
    if user:
        filters["user"] = user
    return frappe.get_all("POS Opening Entry", filters=filters,
                          fields=["name", "user", "pos_profile", "period_start_date"], order_by="period_start_date desc")


def _payment_account(mode_of_payment, company):
    from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account

    return (get_bank_cash_account(mode_of_payment, company) or {}).get("account")


def can_take_payments():
    """
    What ERPNext itself requires from a cashier: create/submit rights on
    the POS invoice doctype, read access to accounts, and read access to
    POS Opening Entry (checked while validating the invoice). With the
    standard roles that means "Accounts User" + "Sales Manager".
    """
    doctype = get_invoice_doctype()
    return bool(
        frappe.has_permission(doctype, "create")
        and frappe.has_permission(doctype, "submit")
        and (frappe.has_permission("Account", "read") or frappe.has_permission("Account", "select"))
        and frappe.has_permission("POS Opening Entry", "read")
    )


@contextmanager
def _as_administrator():
    """
    Run a block with Administrator rights and restore the request's session
    exactly: frappe.set_user() also replaces session.sid / session.data
    (CSRF token…) and form_dict, which would otherwise be saved back and
    log the user out.
    """
    session = frappe.local.session
    saved = (session.user, session.sid, session.data, frappe.local.form_dict)
    try:
        frappe.set_user("Administrator")
        yield
    finally:
        frappe.set_user(saved[0])
        session.sid = saved[1]
        session.data = saved[2]
        frappe.local.form_dict = saved[3]


def tip_settings(profile):
    """{enabled, account, percentages, on} from the POS Profile's Restaurant tab."""
    account = profile.get("ren_tip_account")
    raw = profile.get("ren_tip_percentages") or ""
    percentages = []
    for part in raw.replace(";", ",").split(","):
        try:
            v = float(part.strip().rstrip("%"))
        except ValueError:
            continue
        if 0 < v <= 100:
            percentages.append(v)
    return {
        "enabled": bool(account),
        "account": account,
        "percentages": percentages,
        "on": profile.get("ren_tip_on") or "Subtotal",
    }


def _add_tip(inv, profile, tip):
    tip = flt(tip, inv.precision("grand_total"))
    if tip < 0:
        frappe.throw(_("The tip can't be negative"))
    if not tip:
        return
    settings = tip_settings(profile)
    if not settings["enabled"]:
        frappe.throw(_("Tips are not enabled: set a Tips Account in POS Profile {0}").format(profile.name))
    # a tip above the whole bill is almost surely a typo
    if tip > flt(inv.grand_total):
        frappe.throw(_("The tip ({0}) is larger than the bill").format(tip), title=_("Check the tip"))
    inv.flags.pre_tip_grand_total = flt(inv.grand_total)
    inv.append("taxes", {
        "charge_type": "Actual",
        "account_head": settings["account"],
        "description": _("Tip"),
        "tax_amount": tip,
        "cost_center": profile.cost_center or frappe.get_cached_value("Company", profile.company, "cost_center"),
    })
    inv.ren_tip_amount = tip


def billing_profile_for(order):
    """
    The POS Profile an order is charged with: the cashier's in the order's
    restaurant (their open register first, then the profiles they are listed
    in). Staff who don't charge (a waiter presenting the bill) see it priced
    with the profile the order was taken with.
    """
    from renpos.api.guards import billing_profiles, current_pos_profile, current_restaurant, profile_restaurant
    restaurant = order.get("restaurant") or profile_restaurant(order.pos_profile)
    mine = billing_profiles(restaurant)
    if restaurant == current_restaurant():
        current = current_pos_profile()
        if current in mine:
            return current
    return mine[0] if mine else order.pos_profile


def build_invoice_preview(order, tip=0, loyalty_points=0):
    """
    Same as build_invoice(order, [], tip) but usable by staff who can't create
    invoices themselves (e.g. a waiter presenting the bill): the in-memory
    invoice is built with Administrator rights and never saved.
    """
    profile = billing_profile_for(order)
    if can_take_payments():
        return build_invoice(order, [], tip, loyalty_points, pos_profile=profile)
    with _as_administrator():
        return build_invoice(order, [], tip, loyalty_points, pos_profile=profile)


def opening_status(pos_profile):
    """
    (opening_entry or None, problem or None) for the current cashier.
    problem: "closed" | "outdated"
    """
    opening = get_open_opening_entry(pos_profile)
    if not opening:
        return None, "closed"
    # v16 rejects invoices against a shift opened on a previous day.
    if is_v16_pos() and getdate(opening.period_start_date) != getdate(nowdate()):
        return opening, "outdated"
    return opening, None


def _require_open_register(pos_profile):
    opening, problem = opening_status(pos_profile)
    if problem == "closed":
        frappe.throw(
            _("Open your cash register (POS Opening Entry) for POS Profile {0} before taking payments.").format(
                frappe.bold(pos_profile)
            ),
            title=_("Cash register is closed"),
        )
    if problem == "outdated":
        frappe.throw(
            _("The cash register shift {0} was opened on {1}. Close it (POS Closing Entry) and open a new one.").format(
                frappe.bold(opening.name), frappe.format_value(opening.period_start_date, {"fieldtype": "Datetime"})
            ),
            title=_("Outdated cash register shift"),
        )
    return opening


def payment_modes(profile):
    """Modes of payment enabled in the POS Profile, with their type (Cash/Bank/General/Phone)."""
    return [
        {
            "mode_of_payment": p.mode_of_payment,
            "default": int(p.default or 0),
            "type": frappe.get_cached_value("Mode of Payment", p.mode_of_payment, "type") or "General",
        }
        for p in profile.payments
    ]


def _clean_payments(profile, payments):
    allowed_modes = {p.mode_of_payment for p in profile.payments}
    clean = []
    for p in payments or []:
        mode = p.get("mode_of_payment")
        amount = flt(p.get("amount"))
        if amount == 0:
            continue
        if amount < 0:
            frappe.throw(_("Payment amounts must be positive"))
        if mode not in allowed_modes:
            frappe.throw(_("Mode of payment {0} is not enabled in POS Profile {1}").format(mode, profile.name))
        clean.append((mode, amount))
    return clean


def build_invoice(order, clean_payments, tip=0, loyalty_points=0, pos_profile=None):
    """
    Build the invoice document in memory (not saved) with ERPNext's own
    defaults, taxes and totals. Used for the payment preview and for the
    real invoice, so both show the same numbers.
    """
    profile = frappe.get_cached_doc("POS Profile", pos_profile or billing_profile_for(order))

    doctype = get_invoice_doctype()
    inv = frappe.new_doc(doctype)
    inv.update({
        "is_pos": 1,
        "pos_profile": profile.name,
        "company": profile.company,
        "customer": order.customer or profile.customer,
        "posting_date": nowdate(),
        "selling_price_list": effective_price_list(profile.name),
        "currency": profile.currency,
        "set_warehouse": profile.warehouse,
        "taxes_and_charges": profile.taxes_and_charges,
    })
    # update_stock is a POS Profile field only in some versions;
    # otherwise set_missing_values() applies ERPNext's default.
    if profile.meta.has_field("update_stock"):
        inv.update_stock = profile.update_stock
    if doctype == SALES_INVOICE and inv.meta.has_field("is_created_using_pos"):  # v16
        inv.is_created_using_pos = 1
    # Prices were already validated per row (api.order); ERPNext must not
    # re-apply pricing rules on top of them.
    inv.ignore_pricing_rule = 1

    from renpos.api.modifiers import parse as parse_modifiers

    order_rows = [i for i in order.entry_items if flt(i.qty) > 0]
    priced = []  # (invoice row, order row) whose prices come from the order
    for item in order_rows:
        mods = parse_modifiers(item.get("modifiers"))
        row = inv.append("items", {
            "item_code": item.item_code,
            "qty": item.qty,
            "price_list_rate": item.price_list_rate,
            "discount_percentage": item.discount_percentage,
            "rate": item.rate,
            "warehouse": profile.warehouse,
            "batch_no": item.batch_no or None,
            "serial_no": item.serial_no or None,
        })
        if row.meta.has_field("identifier"):
            row.identifier = item.identifier
        priced.append((row, item, mods))
        # What the options use (ingredients, sides, the parts of a combo)
        # leaves stock once per shift with the recipes (api/recipes.py).

    if not inv.items:
        frappe.throw(_("The order has no items to invoice"))

    # Pull POS Profile defaults (accounts, cost center, taxes, payment rows…).
    # set_pos_fields(for_validate=False) copies the profile's fields, including
    # its ignore_pricing_rule; we then force ignore_pricing_rule = 1 and fill the
    # rest with for_validate=True (which doesn't copy profile fields again), so
    # ERPNext never evaluates pricing rules on top of the validated order prices
    # (conflicting or coupon rules would otherwise throw or add free items).
    if hasattr(inv, "set_pos_fields"):
        inv.set_pos_fields(for_validate=False)
    inv.ignore_pricing_rule = 1
    inv.set_missing_values(for_validate=True)
    if inv.taxes_and_charges and not inv.get("taxes"):
        inv.set_taxes()
    inv.ignore_pricing_rule = 1

    # keep the order's prices on every row; show the options on the receipt
    for row, src, mods in priced:
        row.price_list_rate = src.price_list_rate
        row.discount_percentage = src.discount_percentage
        row.rate = src.rate
        row.pricing_rules = ""
        if mods:
            labels = ", ".join(m["label"] for m in mods)
            row.description = f"{row.item_name or src.item_name}<br><small>{frappe.utils.escape_html(labels)}</small>"
    priced_rows = {id(r) for r, _src, _m in priced}
    for row in inv.items:
        if id(row) not in priced_rows:
            row.price_list_rate = 0
            row.discount_percentage = 0
            row.rate = 0
            row.pricing_rules = ""

    if inv.meta.has_field("ren_server"):
        inv.ren_server = order.owner  # the waiter who opened the order
    # delivery orders: the zone's fee (api/delivery.py)
    from renpos.api.delivery import add_fee
    add_fee(inv, order, profile)
    if tip:
        inv.calculate_taxes_and_totals()
        _add_tip(inv, profile, tip)

    # loyalty points used as part of the payment (api/loyalty.py)
    inv.calculate_taxes_and_totals()
    inv.flags.bill_total = amount_due(inv)
    if cint(loyalty_points):
        from renpos.api.loyalty import apply as apply_loyalty
        apply_loyalty(inv, loyalty_points)

    inv.set("payments", [])
    if not clean_payments and flt(inv.get("loyalty_amount")) and clean_payments is not None:
        # points pay it all: ERPNext still wants a payment row
        default = next((p for p in profile.payments if p.default), None) or (profile.payments[0] if profile.payments else None)
        if default:
            clean_payments = [(default.mode_of_payment, 0)]
    for mode, amount in clean_payments:
        inv.append("payments", {
            "mode_of_payment": mode,
            "amount": amount,
            "account": _payment_account(mode, profile.company),
        })

    inv.calculate_taxes_and_totals()
    inv.flags.order_row_count = len(inv.items)
    return inv


def amount_due(inv):
    """What is left to pay: the bill, less the loyalty points used."""
    total = flt(inv.rounded_total or inv.grand_total) - flt(inv.get("loyalty_amount"))
    return flt(max(total, 0), inv.precision("grand_total"))


def create_invoice(order, payments, tip=0, loyalty_points=0):
    """
    Build, insert and submit the invoice for `order`.

    `payments`: list of {"mode_of_payment": str, "amount": number}.
    Returns the submitted invoice document.
    """
    if not can_take_payments():
        raise frappe.PermissionError(
            _("Your user can't take payments. Ask an administrator for the cashier roles "
              "(Accounts User and Sales Manager, or equivalent permissions).")
        )
    # charged with the cashier's POS Profile (their register), not the one the order was taken with
    from renpos.api.guards import check_billing_profile
    profile_name = billing_profile_for(order)
    check_billing_profile(profile_name)
    _require_open_register(profile_name)

    profile = frappe.get_cached_doc("POS Profile", profile_name)
    clean_payments = _clean_payments(profile, payments)
    if not clean_payments and not cint(loyalty_points):
        frappe.throw(_("At least one payment is required"))

    inv = build_invoice(order, clean_payments, tip, loyalty_points, pos_profile=profile_name)
    _check_paid(inv, clean_payments, profile)

    # can_take_payments() above checked ERPNext's create/submit rights.
    # ignore_permissions is still needed: ignore_pricing_rule is a permlevel-1
    # field that Frappe would reset to 0 for a cashier on insert, making
    # ERPNext re-price the validated order.
    inv.flags.ignore_permissions = True
    inv.insert()

    # Totals after ERPNext's own validation are the ones that count.
    if len(inv.items) != inv.flags.order_row_count:
        frappe.throw(_("The invoice items don't match the order; check pricing rules for free items."))
    _check_paid(inv, clean_payments, profile)

    inv.submit()
    return inv


def _check_paid(inv, clean_payments, profile):
    total_due = amount_due(inv)
    precision = inv.precision("grand_total")
    paid = flt(sum(a for _m, a in clean_payments), precision)
    fmt = lambda v: frappe.format_value(v, {"fieldtype": "Currency", "options": inv.currency})

    if paid < total_due or (not paid and total_due and not clean_payments):
        frappe.throw(
            _("Paid amount {0} is less than the total {1}").format(fmt(paid), fmt(total_due)),
            title=_("Insufficient payment"),
        )

    # Only cash can be overpaid (the difference is given back as change).
    types = {m["mode_of_payment"]: m["type"] for m in payment_modes(profile)}
    non_cash = flt(sum(a for m, a in clean_payments if types.get(m) != "Cash"), precision)
    if non_cash > total_due:
        frappe.throw(
            _("Card/transfer payments ({0}) can't exceed the total {1}").format(fmt(non_cash), fmt(total_due)),
            title=_("Invalid payment"),
        )
