# Copyright (c) 2026, Quantum Bit Core and contributors
# For license information, please see license.txt
"""
Ingredient Usage Variance: what the recipes say was used against what is
really gone from the warehouse, for a period.

Per ingredient (any stock item that moved in the warehouse):

  Opening        stock at the start
  Received       purchases, transfers in, production
  Theoretical    what the recipes took out (Ren's Material Issues, see
                 api/recipes.py) plus what was sold as it is (invoices)
  Waste/Other    other issues out of the warehouse (waste, staff meals,
                 transfers out) recorded by hand
  Closing        stock at the end, after the counts (Stock Reconciliation)
  Actual         Opening + Received - Closing - Waste/Other
  Variance       Theoretical - Actual: negative = more is gone than the
                 recipes explain (over-portioning, unrecorded waste, theft);
                 positive = less is gone (under-portioning, a recipe that
                 asks for too much). It only means something once the
                 period ends with a count.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt

SALES = ("POS Invoice", "Sales Invoice", "Delivery Note")


def execute(filters=None):
    filters = frappe._dict(filters or {})
    for f in ("company", "warehouse", "from_date", "to_date"):
        if not filters.get(f):
            frappe.throw(_("{0} is required").format(_(f.replace("_", " ").title())))
    return columns(), data(filters)


def columns():
    cur = {"fieldtype": "Currency", "width": 110}
    flt_col = {"fieldtype": "Float", "width": 100}
    return [
        {"fieldname": "item_code", "label": _("Ingredient"), "fieldtype": "Link", "options": "Item", "width": 170},
        {"fieldname": "item_name", "label": _("Name"), "fieldtype": "Data", "width": 150},
        {"fieldname": "uom", "label": _("UOM"), "fieldtype": "Link", "options": "UOM", "width": 70},
        {"fieldname": "opening", "label": _("Opening"), **flt_col},
        {"fieldname": "received", "label": _("Received"), **flt_col},
        {"fieldname": "theoretical", "label": _("Theoretical"), **flt_col},
        {"fieldname": "waste", "label": _("Waste / Other"), **flt_col},
        {"fieldname": "closing", "label": _("Closing"), **flt_col},
        {"fieldname": "actual", "label": _("Actual"), **flt_col},
        {"fieldname": "variance_qty", "label": _("Variance"), **flt_col},
        {"fieldname": "variance_pct", "label": _("Variance %"), "fieldtype": "Percent", "width": 95},
        {"fieldname": "unit_cost", "label": _("Unit Cost"), **cur},
        {"fieldname": "variance_value", "label": _("Variance Value"), **cur},
        {"fieldname": "theoretical_value", "label": _("Theoretical Cost"), **cur},
    ]


def recipe_entries(company, from_date, to_date):
    """Ren's recipe Material Issues (the ones paid orders point to)."""
    return set(frappe.db.sql_list("""
        SELECT DISTINCT se.name FROM `tabStock Entry` se
        JOIN `tabRen Order` o ON o.ren_usage_entry = se.name
        WHERE se.company = %s AND se.docstatus = 1 AND se.posting_date BETWEEN %s AND %s
    """, (company, from_date, to_date)))


def data(filters):
    conditions = ["sle.warehouse = %(warehouse)s", "sle.is_cancelled = 0", "sle.company = %(company)s"]
    if filters.item_group:
        lft, rgt = frappe.db.get_value("Item Group", filters.item_group, ["lft", "rgt"])
        groups = frappe.get_all("Item Group", filters={"lft": [">=", lft], "rgt": ["<=", rgt]}, pluck="name")
        conditions.append("item.item_group IN %(groups)s")
        filters.groups = groups
    where = " AND ".join(conditions)

    moves = frappe.db.sql(f"""
        SELECT sle.item_code, sle.voucher_type, sle.voucher_no, sle.actual_qty
        FROM `tabStock Ledger Entry` sle JOIN `tabItem` item ON item.name = sle.item_code
        WHERE {where} AND sle.posting_date BETWEEN %(from_date)s AND %(to_date)s
          AND sle.voucher_type != 'Stock Reconciliation'
    """, filters, as_dict=True)
    items = {m.item_code for m in moves}
    # items only counted in the period count too (nothing else moved)
    items |= set(frappe.db.sql_list(f"""
        SELECT DISTINCT sle.item_code FROM `tabStock Ledger Entry` sle JOIN `tabItem` item ON item.name = sle.item_code
        WHERE {where} AND sle.posting_date BETWEEN %(from_date)s AND %(to_date)s
    """, filters))
    if not items:
        return []

    recipes = recipe_entries(filters.company, filters.from_date, filters.to_date)
    rows = {code: frappe._dict(received=0, theoretical=0, waste=0) for code in items}
    for m in moves:
        r = rows[m.item_code]
        q = flt(m.actual_qty)
        if q > 0:
            r.received += q
        elif m.voucher_type in SALES or (m.voucher_type == "Stock Entry" and m.voucher_no in recipes):
            r.theoretical += -q
        else:
            r.waste += -q

    from erpnext.stock.stock_ledger import get_previous_sle
    start = add_days(filters.from_date, -1)
    out = []
    meta = {i.name: i for i in frappe.get_all("Item", filters={"name": ["in", list(items)]},
                                              fields=["name", "item_name", "stock_uom", "valuation_rate"])}
    for code in sorted(items):
        r = rows[code]
        args = {"item_code": code, "warehouse": filters.warehouse}
        opening = flt(get_previous_sle({**args, "posting_date": start, "posting_time": "23:59:59"}).get("qty_after_transaction"))
        last = get_previous_sle({**args, "posting_date": filters.to_date, "posting_time": "23:59:59"})
        closing = flt(last.get("qty_after_transaction"))
        unit = flt(last.get("valuation_rate")) or flt(meta[code].valuation_rate)
        actual = opening + r.received - closing - r.waste
        variance = r.theoretical - actual
        if filters.only_variance and abs(variance) < 1e-6:
            continue
        out.append({
            "item_code": code, "item_name": meta[code].item_name, "uom": meta[code].stock_uom,
            "opening": opening, "received": r.received, "theoretical": r.theoretical, "waste": r.waste,
            "closing": closing, "actual": actual, "variance_qty": variance,
            "variance_pct": (variance / actual * 100) if actual else 0,
            "unit_cost": unit, "variance_value": variance * unit, "theoretical_value": r.theoretical * unit,
        })
    out.sort(key=lambda d: d["variance_value"])
    return out
