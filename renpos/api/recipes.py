# -*- coding: utf-8 -*-
# renpos/api/recipes.py
#
# Recipes: what the kitchen uses to make one unit of a dish, taken out of
# stock when the dish is sold.
#
#   The recipe is an ERPNext BOM: Item.ren_recipe, or the item's default BOM.
#   Only for dishes that aren't stock items (the dish isn't kept in stock;
#   its ingredients are). Stock items keep ERPNext's own behaviour.
#
#   A variant (a size) uses its own BOM, else its template's.
#
#   What was chosen adjusts it (api/modifiers.py). Each option whose
#   component is a line of the recipe sets how many portions of that line go
#   in (removed = 0, light = 0.5, extra = 2...). Any other component adds
#   what it is made of, times its portion: an ingredient (a stock item) adds
#   itself; a dish (a burger inside a combo, a side) adds its own recipe,
#   adjusted by what was chosen for it; a component with sizes adds the
#   size chosen. So a combo with no recipe of its own takes out exactly
#   what its parts use.
#
#   Nothing is posted per sale. Paid orders (Ren Order "Invoiced") are
#   gathered and their ingredients taken out with ONE Stock Entry "Material
#   Issue" per POS Profile: when a cashier closes their register, and daily
#   for anything left. The entry goes to the company's cost of goods sold.
#   Orders already counted carry it in ren_usage_entry; orders with nothing
#   to take out are marked so they aren't looked at again.
#
# Only POS Profiles with "Update Stock" on take stock out (same rule as the
# invoices).

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

from renpos.api.modifiers import parse, portions

NOTHING = "-"  # ren_usage_entry of a paid order with nothing to take out


# ─────────────────────────────────────────────
# Which recipe
# ─────────────────────────────────────────────

def recipe_of(item_code):
    """The BOM used as the dish's recipe, or None (stock items never have one here)."""
    row = frappe.get_cached_value("Item", item_code, ["is_stock_item", "default_bom", "variant_of"], as_dict=True)
    if not row or cint(row.is_stock_item):
        return None
    bom = None
    if frappe.get_meta("Item").has_field("ren_recipe"):
        bom = frappe.get_cached_value("Item", item_code, "ren_recipe")
    bom = bom or row.default_bom
    if bom and frappe.db.get_value("BOM", bom, "is_active") and frappe.db.get_value("BOM", bom, "docstatus") == 1:
        return bom
    if row.variant_of:
        return recipe_of(row.variant_of)  # a size without its own recipe: the template's
    return None


def recipe_lines(bom):
    """{item: qty in its stock unit for ONE unit of the dish}"""
    doc = frappe.get_cached_doc("BOM", bom)
    per = flt(doc.quantity) or 1
    out = {}
    for r in doc.items:
        out[r.item_code] = out.get(r.item_code, 0) + flt(r.stock_qty or r.qty) / per
    return out


def unit_cost(item_code):
    """Current cost of one stock unit: the stock's average valuation, else the item's valuation / last purchase."""
    row = frappe.db.sql("""SELECT SUM(stock_value), SUM(actual_qty) FROM `tabBin`
        WHERE item_code = %s AND actual_qty > 0""", item_code)
    if row and flt(row[0][1]) > 0:
        return flt(row[0][0]) / flt(row[0][1])
    rates = frappe.db.get_value("Item", item_code, ["valuation_rate", "last_purchase_rate"]) or (0, 0)
    return flt(rates[0]) or flt(rates[1])


def recipe_cost(bom):
    """
    Cost of ONE unit: each ingredient's quantity x its current cost. Worked out
    here rather than read from the BOM's costing, which rounds every rate to
    the currency's precision (a gram of tomato at 0.005 becomes 0.00).
    """
    if not bom:
        return 0
    return flt(sum(qty * unit_cost(code) for code, qty in recipe_lines(bom).items()), 4)


def _lines(item_code, cache):
    if item_code not in cache:
        bom = recipe_of(item_code)
        cache[item_code] = recipe_lines(bom) if bom else {}
    return cache[item_code]


def _add(out, more, factor=1):
    for k, v in more.items():
        out[k] = out.get(k, 0) + v * factor


def _usage(item_code, entries, kids, cache, top=True):
    """{ingredient: qty} for ONE unit of item_code made with `entries` (its chosen options)."""
    lines = _lines(item_code, cache)
    out = dict(lines)
    in_recipe = {}
    for e in entries:
        comp = e.get("item")
        if not comp:
            continue  # an instruction for the kitchen
        n = portions(e)
        if comp in lines:
            in_recipe[comp] = in_recipe.get(comp, 0) + n
            continue
        if not n:
            continue
        _add(out, _component(comp, kids.get(e.get("option"), []) if top else [], cache), n * (flt(e.get("ingredient_qty")) or 1))
    for comp, n in in_recipe.items():
        out[comp] = lines[comp] * n
    return out


def _component(comp, sub, cache):
    """{ingredient: qty} for ONE portion of a component, with what was chosen for it."""
    meta = frappe.get_cached_value("Item", comp, ["is_stock_item", "has_variants"], as_dict=True) or frappe._dict()
    if cint(meta.has_variants):
        size = next((e for e in sub if e.get("variant") and not e.get("removed")), None)
        if not size:
            return {}
        return _component(size["item"], [e for e in sub if e is not size], cache)
    if recipe_of(comp) or sub:
        used = _usage(comp, sub, {}, cache, top=False)
        if used or not cint(meta.is_stock_item):
            return used
    return {comp: 1} if cint(meta.is_stock_item) else {}


def line_usage(item_code, qty, modifiers, cache=None):
    """
    {ingredient: qty} used by an order line (qty units of item_code with its
    options), or {} when nothing it is made of is known.
    """
    cache = cache if cache is not None else {}
    entries = parse(modifiers)
    top = [e for e in entries if not e.get("parent")]
    kids = {}
    for e in entries:
        if e.get("parent"):
            kids.setdefault(e["parent"], []).append(e)
    if cint(frappe.get_cached_value("Item", item_code, "is_stock_item")):
        # sold from stock by the invoice; only what was added to it is counted here
        used = {}
        for e in top:
            if e.get("item") and not e.get("included") and portions(e):
                _add(used, _component(e["item"], kids.get(e.get("option"), []), cache),
                     portions(e) * (flt(e.get("ingredient_qty")) or 1))
    else:
        used = _usage(item_code, top, kids, cache)
    return {k: flt(v * flt(qty), 6) for k, v in used.items() if flt(v * flt(qty), 6) > 0}


# ─────────────────────────────────────────────
# Item form: recipe cost
# ─────────────────────────────────────────────

def item_validate(doc, method=None):
    """Item hook: a recipe belongs to this dish, the dish isn't a stock item; keep its cost shown."""
    if not doc.meta.has_field("ren_recipe"):
        return
    if doc.ren_recipe:
        if frappe.db.get_value("BOM", doc.ren_recipe, "item") != doc.name:
            frappe.throw(_("The recipe {0} is a BOM of another item").format(frappe.bold(doc.ren_recipe)))
        if cint(doc.is_stock_item):
            frappe.throw(_("A dish with a recipe isn't kept in stock: turn off Maintain Stock. "
                           "Its ingredients are taken out when it's sold."), title=_("Recipe"))
    if doc.meta.has_field("ren_recipe_cost"):
        bom = doc.ren_recipe or (doc.default_bom if not cint(doc.is_stock_item) else None)
        doc.ren_recipe_cost = recipe_cost(bom) if bom else 0


# ─────────────────────────────────────────────
# Taking ingredients out of stock
# ─────────────────────────────────────────────

def _pending_orders(pos_profile=None):
    filters = {"status": "Invoiced", "ren_usage_entry": ["in", ["", None]]}
    if pos_profile:
        filters["pos_profile"] = pos_profile
    return frappe.get_all("Ren Order", filters=filters, fields=["name", "pos_profile"], order_by="modified asc",
                          limit_page_length=0)


def usage_of_orders(order_names):
    """{ingredient: qty} of paid orders, and which of them had something to take out."""
    total, with_usage, cache = {}, set(), {}
    if not order_names:
        return total, with_usage
    rows = frappe.get_all("Ren Order Item", filters={"parenttype": "Ren Order", "parent": ["in", order_names],
                                                      "qty": [">", 0]},
                          fields=["parent", "item_code", "qty", "modifiers"])
    for r in rows:
        used = line_usage(r.item_code, r.qty, r.modifiers, cache)
        if used:
            with_usage.add(r.parent)
        for k, v in used.items():
            total[k] = total.get(k, 0) + v
    return total, with_usage


def post_usage(pos_profile):
    """
    Take the ingredients of the POS Profile's paid orders not counted yet out
    of its warehouse with one Material Issue. Returns the Stock Entry name,
    "" when there was nothing to take out, or None when it couldn't be posted
    (the orders stay pending; the error is in the Error Log).
    """
    profile = frappe.get_cached_doc("POS Profile", pos_profile)
    if not cint(profile.get("update_stock")):
        return ""
    lock = f"ren_recipe_usage:{pos_profile}"
    if frappe.cache.get_value(lock):
        return None
    frappe.cache.set_value(lock, 1, expires_in_sec=300)
    try:
        orders = [o.name for o in _pending_orders(pos_profile)]
        if not orders:
            return ""
        total, with_usage = usage_of_orders(orders)
        nothing = [o for o in orders if o not in with_usage]
        if nothing:
            frappe.db.sql("""UPDATE `tabRen Order` SET ren_usage_entry = %s WHERE name IN %s""",
                          (NOTHING, tuple(nothing)))
        if not total:
            return ""
        company = profile.company
        expense = frappe.get_cached_value("Company", company, "default_expense_account")
        cost_center = profile.get("cost_center") or frappe.get_cached_value("Company", company, "cost_center")
        se = frappe.new_doc("Stock Entry")
        se.stock_entry_type = "Material Issue"
        se.purpose = "Material Issue"
        se.company = company
        se.from_warehouse = profile.warehouse
        se.set_posting_time = 1
        se.posting_date = now_datetime().date()
        se.posting_time = now_datetime().time()
        se.remarks = _("Ingredients used by {0} paid orders of {1} (restaurant recipes)").format(
            len(with_usage), pos_profile)
        for item_code, qty in sorted(total.items()):
            row = se.append("items", {
                "item_code": item_code,
                "qty": flt(qty, 6),
                "s_warehouse": profile.warehouse,
                "uom": frappe.get_cached_value("Item", item_code, "stock_uom"),
                "conversion_factor": 1,
            })
            if expense:
                row.expense_account = expense
            if cost_center:
                row.cost_center = cost_center
        se.flags.ignore_permissions = True
        frappe.db.savepoint("ren_recipe_usage")
        try:
            se.insert()
            se.submit()
        except Exception:
            frappe.db.rollback(save_point="ren_recipe_usage")
            frappe.log_error(title=_("Restaurant: ingredients not taken out of stock"),
                             reference_doctype="POS Profile", reference_name=pos_profile)
            return None
        frappe.db.sql("""UPDATE `tabRen Order` SET ren_usage_entry = %s WHERE name IN %s""",
                      (se.name, tuple(with_usage)))
        return se.name
    finally:
        frappe.cache.delete_value(lock)


def post_pending_usage():
    """Daily: every POS Profile with paid orders whose ingredients weren't taken out yet."""
    if not frappe.db.has_column("Ren Order", "ren_usage_entry"):
        return
    for profile in {o.pos_profile for o in _pending_orders() if o.pos_profile}:
        post_usage(profile)
        frappe.db.commit()


@frappe.whitelist()
def get_recipe_info(item_code):
    """Recipe, cost and price of a dish (item form and reports)."""
    from renpos.api.guards import require_restaurant_user
    require_restaurant_user()
    bom = recipe_of(item_code)
    lines = recipe_lines(bom) if bom else {}
    return {"recipe": bom, "cost": recipe_cost(bom), "ingredients": [
        {"item_code": k, "item_name": frappe.get_cached_value("Item", k, "item_name"), "qty": v,
         "uom": frappe.get_cached_value("Item", k, "stock_uom")} for k, v in lines.items()]}
