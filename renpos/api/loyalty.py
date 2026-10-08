# -*- coding: utf-8 -*-
# renpos/api/loyalty.py
#
# Loyalty points at the restaurant, on ERPNext's own Loyalty Program:
#
#   Earning   the invoice of a customer enrolled in a program (Customer
#             loyalty_program, same company) earns points when it is
#             submitted — ERPNext does it (Loyalty Point Entry).
#   Redeeming at payment the cashier can use the customer's points as part
#             of the payment: the invoice gets redeem_loyalty_points,
#             loyalty_points and loyalty_amount (points x the program's
#             conversion factor), which ERPNext counts as paid and books to
#             the program's expense account.
#
# Points earned on a POS Invoice are redeemed on POS Invoices (ERPNext only
# redeems against the same invoice type).

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, today


def program_of(customer, company):
    """The customer's Loyalty Program if it is valid today for that company, else None."""
    if not customer:
        return None
    name = frappe.db.get_value("Customer", customer, "loyalty_program")
    if not name:
        return None
    lp = frappe.get_cached_doc("Loyalty Program", name)
    if lp.company and lp.company != company:
        return None
    if lp.from_date and getdate(lp.from_date) > getdate(today()):
        return None
    if lp.to_date and getdate(lp.to_date) < getdate(today()):
        return None
    return lp


def _points(customer, program, company):
    """Points the customer can use today (not expired)."""
    from erpnext.accounts.doctype.loyalty_program.loyalty_program import get_loyalty_details
    return cint(get_loyalty_details(customer, program, expiry_date=today(), company=company).get("loyalty_points"))


def _tier(lp, customer, company, amount):
    """(tier name, collection factor) after this purchase."""
    from erpnext.accounts.doctype.loyalty_program.loyalty_program import get_loyalty_details
    spent = flt(get_loyalty_details(customer, lp.name, company=company, include_expired_entry=True).get("total_spent"))
    tier, factor = None, 1.0
    for i, r in enumerate(sorted(lp.collection_rules, key=lambda r: flt(r.min_spent))):
        if i == 0 or spent + flt(amount) >= flt(r.min_spent):
            tier, factor = r.tier_name, flt(r.collection_factor) or 1.0
        else:
            break
    return tier, factor


def info(customer, company, total, redeemed_amount=0):
    """
    What the payment screen shows, or None when the customer isn't in a program:
    {program, tier, points, point_value, value, max_points, earns}.
    `total` = the bill before any points are used.
    """
    lp = program_of(customer, company)
    if not lp:
        return None
    points = _points(customer, lp.name, company)
    value = flt(lp.conversion_factor)
    max_points = min(points, int(flt(total) / value)) if value > 0 else 0
    tier, collection = _tier(lp, customer, company, total)
    earns = cint((flt(total) - flt(redeemed_amount)) / collection) if collection else 0
    return {
        "program": lp.name,
        "tier": tier,
        "points": points,
        "point_value": value,
        "value": flt(points * value, 2),
        "max_points": max(max_points, 0),
        "earns": max(earns, 0),
    }


def apply(inv, points):
    """Use `points` of the invoice customer's points as payment (validated here; ERPNext re-checks on save)."""
    points = cint(points)
    if points <= 0:
        return
    lp = program_of(inv.customer, inv.company)
    if not lp:
        frappe.throw(_("{0} isn't in a loyalty program").format(frappe.bold(inv.customer_name or inv.customer)))
    if not lp.expense_account or not lp.cost_center:
        frappe.throw(_("Loyalty Program {0} needs an Expense Account and a Cost Center to redeem points").format(
            frappe.bold(lp.name)), title=_("Loyalty"))
    available = _points(inv.customer, lp.name, inv.company)
    if points > available:
        frappe.throw(_("The customer has only {0} points").format(available), title=_("Loyalty"))
    amount = flt(points * flt(lp.conversion_factor), inv.precision("grand_total"))
    total = flt(inv.rounded_total or inv.grand_total)
    if amount > total:
        frappe.throw(_("Points worth {0} can't pay a bill of {1}").format(amount, total), title=_("Loyalty"))
    inv.loyalty_program = lp.name
    inv.redeem_loyalty_points = 1
    inv.loyalty_points = points
    inv.loyalty_amount = amount
    inv.loyalty_redemption_account = lp.expense_account
    inv.loyalty_redemption_cost_center = lp.cost_center


def program_to_join(customer, company, walk_in=None):
    """The program a guest can join at the register: none for the walk-in customer or someone already in one."""
    if not customer or customer == walk_in or frappe.db.get_value("Customer", customer, "loyalty_program"):
        return None
    rows = frappe.get_all("Loyalty Program", filters={"company": ["in", [company, ""]]},
                          fields=["name", "auto_opt_in", "from_date", "to_date"], order_by="auto_opt_in desc, creation asc")
    for r in rows:
        if (not r.from_date or getdate(r.from_date) <= getdate(today())) and \
                (not r.to_date or getdate(r.to_date) >= getdate(today())):
            return r.name
    return None


@frappe.whitelist()
def join(order_name):
    """Enroll the order's customer in the restaurant's loyalty program (the cashier, with the guest's consent)."""
    from renpos.api import access
    from renpos.api.order import get_order
    order = get_order(order_name, "write")
    access.require("take_payments", order.pos_profile, reference=("Ren Order", order.name))
    from renpos.api.invoicing import billing_profile_for
    profile = frappe.get_cached_doc("POS Profile", billing_profile_for(order))
    customer = order.customer or profile.customer
    program = program_to_join(customer, profile.company, profile.customer)
    if not program:
        frappe.throw(_("This customer can't join a loyalty program here"), title=_("Loyalty"))
    frappe.db.set_value("Customer", customer, "loyalty_program", program)
    from renpos.api.access import audit
    audit("Loyalty enrollment", reference=("Customer", customer), detail=program)
    return {"customer": customer, "program": program}
