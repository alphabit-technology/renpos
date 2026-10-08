# -*- coding: utf-8 -*-
# renpos/api/item_editor.py
#
# The Menu Manager's item editor. It edits the ERPNext Item itself (see the
# project decision "una sola gestión de artículos"): what is the item's is
# saved on the Item (name, group, photo, description, tags, the Restaurant
# tab: sections, options, combo settings) and its price on the restaurant's
# price list; what is the menu's is saved on the menu (in it or not, menu
# price). Nothing here is a second copy: the desk form shows the same data.
#
# Needs the "edit menus" action of the person's Ren Role (or a PIN).

import json
import re

import frappe
from frappe import _
from frappe.utils import cint, flt

from renpos.api import access
from renpos.api.guards import current_pos_profile, effective_price_list, require_restaurant_user

SECTION_FIELDS = ("section", "option_list", "min_select", "max_select", "free_choices", "use_modes", "price_by_size")
OPTION_FIELDS = ("section", "role", "item", "label", "price", "changes_price", "max_qty", "qty", "preselected",
                 "variant", "unavailable")


def _price_list():
	profile = current_pos_profile()
	return effective_price_list(profile) if profile else frappe.db.get_single_value("Selling Settings", "selling_price_list")


def _parse(value):
	if isinstance(value, str):
		value = json.loads(value or "{}")
	return frappe._dict(value or {})


def _base_price(item_code, price_list):
	return frappe.db.get_value("Item Price", {"item_code": item_code, "price_list": price_list, "selling": 1,
	                                          "customer": ["in", ["", None]], "batch_no": ["in", ["", None]]},
	                           "price_list_rate")


@frappe.whitelist()
def get_item(item_code, menu=None):
	"""Everything the editor shows for one item."""
	require_restaurant_user()
	access.require("edit_menu")
	doc = frappe.get_doc("Item", item_code)
	price_list = _price_list()
	row = frappe.db.get_value("Ren Menu Item", {"parent": menu, "parenttype": "Ren Menu", "item": item_code},
	                          ["enabled", "rate"], as_dict=True) if menu else None
	return {
		"item": {
			"item_code": doc.name,
			"item_name": doc.item_name,
			"item_group": doc.item_group,
			"description": doc.description or "",
			"image": doc.image or "",
			"disabled": cint(doc.disabled),
			"is_stock_item": cint(doc.is_stock_item),
			"has_variants": cint(doc.has_variants),
			"variant_of": doc.variant_of,
			"tags": [t.tag for t in doc.get("ren_tags") or []],
			"price": flt(_base_price(doc.name, price_list)) if not doc.has_variants else None,
			"price_from_components": cint(doc.get("ren_price_from_components")),
			"route_components": cint(doc.get("ren_route_components")),
			"sections": [{f: s.get(f) for f in SECTION_FIELDS} for s in doc.get("ren_option_sections") or []],
			"options": [{**{f: o.get(f) for f in OPTION_FIELDS},
			             "item_name": frappe.get_cached_value("Item", o.item, "item_name") if o.item else None}
			            for o in doc.get("ren_options") or []],
		},
		"sizes": _sizes(doc, price_list),
		"recipe": _recipe(doc.name),
		"sold": _was_sold(doc.name),
		"menu": {"name": menu, "in_menu": bool(row and cint(row.enabled)), "rate": flt(row.rate) if row else 0}
		if menu else None,
		"price_list": price_list,
		"currency": frappe.db.get_value("Price List", price_list, "currency"),
	}


@frappe.whitelist()
def get_lookups():
	"""Item groups, option lists and menu tags for the editor's pickers."""
	require_restaurant_user()
	access.require("edit_menu")
	return {
		"item_groups": frappe.get_all("Item Group", filters={"is_group": 0}, pluck="name", order_by="name asc"),
		"option_lists": frappe.get_all("Ren Option List", pluck="name", order_by="name asc"),
		"tags": frappe.get_all("Ren Menu Tag", fields=["name", "kind", "abbreviation", "color"], order_by="kind asc, name asc"),
		# attributes a size can be made of (Size, Crust...), with their values in order
		"attributes": [{"name": a, "values": frappe.get_all("Item Attribute Value", filters={"parent": a},
		                                                      pluck="attribute_value", order_by="idx asc")}
		               for a in frappe.get_all("Item Attribute", filters={"numeric_values": 0}, pluck="name",
		                                       order_by="name asc")],
	}


@frappe.whitelist()
def search_items(txt="", limit=20):
	"""Items to use as a combo component or an option (sales items and ingredients)."""
	require_restaurant_user()
	access.require("edit_menu")
	txt = (txt or "").strip()
	filters = {"disabled": 0, "variant_of": ["is", "not set"]}
	or_filters = {"item_name": ["like", f"%{txt}%"], "name": ["like", f"%{txt}%"]} if txt else None
	return frappe.get_all("Item", filters=filters, or_filters=or_filters,
	                      fields=["name as item_code", "item_name", "item_group", "is_sales_item", "has_variants", "image"],
	                      order_by="is_sales_item desc, item_name asc", limit=cint(limit) or 20)


def _new_code(name):
	base = re.sub(r"[^A-Z0-9]+", "-", (name or "").upper()).strip("-")[:120] or "ITEM"
	code, n = base, 1
	while frappe.db.exists("Item", code):
		n += 1
		code = f"{base}-{n}"
	return code


@frappe.whitelist()
def save_item(data, menu=None):
	"""
	Create (no item_code) or update an item from the editor:
	data = {item_code?, item_name, item_group, description, image, tags,
	        price, price_from_components, route_components, sections, options,
	        is_stock_item (new items only)}
	and, with a menu, {in_menu, menu_rate}.
	"""
	require_restaurant_user()
	access.require("edit_menu")
	data = _parse(data)
	name = (data.item_name or "").strip()
	if not name:
		frappe.throw(_("The item needs a name"))

	if data.item_code:
		doc = frappe.get_doc("Item", data.item_code)
	else:
		doc = frappe.new_doc("Item")
		doc.item_code = _new_code(name)
		doc.is_sales_item = 1
		doc.is_stock_item = cint(data.is_stock_item)
		doc.include_item_in_manufacturing = 0
		doc.stock_uom = frappe.db.get_single_value("Stock Settings", "stock_uom") or "Nos"

	doc.item_name = name[:140]
	if data.item_group:
		doc.item_group = data.item_group
	if not doc.item_group:
		frappe.throw(_("Choose the item's group"))
	doc.description = data.description or doc.item_name
	doc.image = data.image or None

	if doc.meta.has_field("ren_tags") and data.tags is not None:
		doc.set("ren_tags", [{"tag": t} for t in data.tags if t])
	if doc.meta.has_field("ren_options"):
		doc.ren_price_from_components = cint(data.price_from_components)
		doc.ren_route_components = cint(data.route_components)
		if data.sections is not None:
			doc.set("ren_option_sections", [{f: s.get(f) for f in SECTION_FIELDS if s.get(f) not in (None, "")}
			                               for s in data.sections])
		if data.options is not None:
			doc.set("ren_options", [{f: o.get(f) for f in OPTION_FIELDS if o.get(f) not in (None, "")}
			                       for o in data.options if o.get("item") or (o.get("label") or "").strip()])

	sizes = data.sizes if isinstance(data.sizes, dict) else None
	if sizes is not None and sizes.get("values"):
		_make_template(doc, sizes)

	doc.flags.ignore_permissions = True
	doc.save() if not doc.is_new() else doc.insert()

	if sizes is not None and cint(doc.has_variants):
		_save_sizes(doc, sizes)
	if data.recipe is not None:
		_save_recipe(doc, data.recipe)

	# price on the restaurant's price list (a template's price is its sizes')
	price_list = _price_list()
	if data.price is not None and data.price != "" and not cint(doc.has_variants) and price_list:
		_set_price(doc.name, price_list, flt(data.price))

	if menu and data.in_menu is not None:
		from renpos.api.menus import set_menu_item
		rate = flt(data.menu_rate) if flt(data.menu_rate) > 0 else 0
		set_menu_item(menu, doc.name, enabled=cint(data.in_menu), rate=rate)

	frappe.publish_realtime("menu_changed", {"menu": menu, "item": doc.name}, after_commit=True)
	return get_item(doc.name, menu)


def _set_price(item_code, price_list, rate):
	name = frappe.db.get_value("Item Price", {"item_code": item_code, "price_list": price_list, "selling": 1,
	                                          "customer": ["in", ["", None]], "batch_no": ["in", ["", None]]})
	if name:
		if flt(frappe.db.get_value("Item Price", name, "price_list_rate")) != rate:
			ip = frappe.get_doc("Item Price", name)
			ip.price_list_rate = rate
			ip.flags.ignore_permissions = True
			ip.save()
		return
	frappe.get_doc({"doctype": "Item Price", "item_code": item_code, "price_list": price_list,
	                "price_list_rate": rate}).insert(ignore_permissions=True)


# ─────────────────────────────────────────────
# Sizes: ERPNext variants of the item
# ─────────────────────────────────────────────

SALE_TABLES = ("Sales Invoice Item", "POS Invoice Item", "Ren Order Item")


def _was_sold(item_code):
	return any(frappe.db.exists(t, {"item_code": item_code}) for t in SALE_TABLES) \
		or bool(frappe.db.exists("Stock Ledger Entry", {"item_code": item_code}))


def _sizes(doc, price_list):
	"""{attribute, values: [{value, item_code, price, enabled}]} of a template, else None."""
	if not cint(doc.has_variants):
		return None
	attribute = (doc.get("attributes") or [frappe._dict()])[0].get("attribute")
	rows = frappe.get_all("Item", filters={"variant_of": doc.name}, fields=["name", "disabled"])
	values = {r.parent: r.attribute_value for r in frappe.get_all(
		"Item Variant Attribute", filters={"parent": ["in", [r.name for r in rows] or [""]], "attribute": attribute},
		fields=["parent", "attribute_value"])}
	order = {v: i for i, v in enumerate(frappe.get_all("Item Attribute Value", filters={"parent": attribute},
	                                                   pluck="attribute_value", order_by="idx asc"))}
	out = [{"value": values.get(r.name) or r.name, "item_code": r.name, "enabled": not cint(r.disabled),
	        "price": flt(_base_price(r.name, price_list))} for r in rows]
	out.sort(key=lambda v: (order.get(v["value"], 999), v["item_code"]))
	return {"attribute": attribute, "values": out}


def _ensure_attribute(attribute, values):
	"""The Item Attribute with every value (new values are added at the end)."""
	attribute = (attribute or "Size").strip()
	if not frappe.db.exists("Item Attribute", attribute):
		frappe.get_doc({"doctype": "Item Attribute", "attribute_name": attribute}).insert(ignore_permissions=True)
	doc = frappe.get_doc("Item Attribute", attribute)
	if cint(doc.numeric_values):
		frappe.throw(_("{0} has numeric values: choose another attribute for the sizes").format(frappe.bold(attribute)))
	have = {v.attribute_value for v in doc.item_attribute_values}
	abbrs = {v.abbr for v in doc.item_attribute_values}
	added = False
	for value in values:
		if value in have:
			continue
		abbr = re.sub(r"[^A-Za-z0-9]", "", value).upper()[:3] or "X"
		base, n = abbr, 1
		while abbr in abbrs:
			n += 1
			abbr = f"{base}{n}"
		doc.append("item_attribute_values", {"attribute_value": value, "abbr": abbr})
		have.add(value)
		abbrs.add(abbr)
		added = True
	if added:
		doc.flags.ignore_permissions = True
		doc.save()
	return attribute


def _make_template(doc, sizes):
	"""Turn the item into a template with sizes (only one that was never sold or stocked)."""
	if cint(doc.has_variants):
		return
	attribute = _ensure_attribute(sizes.get("attribute"),
	                              [v["value"].strip() for v in sizes.get("values") or [] if (v.get("value") or "").strip()])
	if doc.variant_of:
		frappe.throw(_("{0} is already a size of {1}").format(frappe.bold(doc.item_name), frappe.bold(doc.variant_of)))
	if not doc.is_new() and _was_sold(doc.name):
		frappe.throw(_("{0} has already been sold: sizes can only be added to a new item. Create the item again "
		               "with its sizes and take the old one off the menu.").format(frappe.bold(doc.item_name)),
		             title=_("Sizes"))
	doc.has_variants = 1
	doc.set("attributes", [{"attribute": attribute}])


def _save_sizes(doc, sizes):
	"""sizes = {attribute, values: [{value, price, enabled}]}: a variant per value, its price, enabled or not."""
	from erpnext.controllers.item_variant import create_variant
	attribute = (doc.get("attributes") or [frappe._dict()])[0].get("attribute")
	rows = [v for v in (sizes.get("values") or []) if (v.get("value") or "").strip()]
	if not rows:
		return
	_ensure_attribute(attribute, [v["value"].strip() for v in rows])
	price_list = _price_list()
	existing = {r.attribute_value: r.parent for r in frappe.get_all(
		"Item Variant Attribute", filters={"variant_of": doc.name, "attribute": attribute},
		fields=["parent", "attribute_value"])}
	for v in rows:
		value = v["value"].strip()
		code = existing.get(value)
		if not code:
			variant = create_variant(doc.name, {attribute: value})
			variant.is_stock_item = doc.is_stock_item
			variant.flags.ignore_permissions = True
			variant.insert()
			code = variant.name
		enabled = cint(v.get("enabled", 1))
		if cint(frappe.db.get_value("Item", code, "disabled")) == enabled:
			frappe.db.set_value("Item", code, "disabled", 0 if enabled else 1)
		if v.get("price") not in (None, "") and price_list:
			_set_price(code, price_list, flt(v["price"]))


# ─────────────────────────────────────────────
# Recipe: the dish's BOM
# ─────────────────────────────────────────────

def _recipe(item_code):
	from renpos.api.recipes import recipe_cost, recipe_lines, recipe_of, unit_cost
	bom = recipe_of(item_code)
	own = bom and frappe.db.get_value("BOM", bom, "item") == item_code
	lines = recipe_lines(bom) if bom else {}
	return {
		"bom": bom,
		"inherited": bool(bom and not own),  # a size using its template's recipe
		"cost": recipe_cost(bom),
		"lines": [{"item_code": k, "item_name": frappe.get_cached_value("Item", k, "item_name"), "qty": flt(q, 6),
		           "uom": frappe.get_cached_value("Item", k, "stock_uom"), "unit_cost": flt(unit_cost(k), 4)}
		          for k, q in lines.items()],
	}


def _save_recipe(doc, lines):
	"""A new BOM with these lines becomes the dish's recipe (BOMs are submitted: the old one is deactivated)."""
	from renpos.api.recipes import recipe_lines
	lines = [l for l in (lines or []) if l.get("item_code") and flt(l.get("qty")) > 0]
	current = doc.get("ren_recipe") or doc.default_bom
	if current and frappe.db.get_value("BOM", current, "item") != doc.name:
		current = None
	want = {}
	for l in lines:
		want[l["item_code"]] = want.get(l["item_code"], 0) + flt(l["qty"])
	if current and {k: flt(v, 6) for k, v in recipe_lines(current).items()} == {k: flt(v, 6) for k, v in want.items()}:
		return  # unchanged
	if want and cint(doc.is_stock_item):
		frappe.throw(_("A dish with a recipe isn't kept in stock: turn off \"Keep stock of this item\" in the desk, "
		               "or leave the recipe empty."), title=_("Recipe"))
	if current:
		frappe.db.set_value("BOM", current, {"is_active": 0, "is_default": 0})
	new = None
	if want:
		profile = current_pos_profile()
		company = frappe.db.get_value("POS Profile", profile, "company") if profile else frappe.defaults.get_user_default("company")
		bom = frappe.get_doc({"doctype": "BOM", "item": doc.name, "company": company, "quantity": 1,
		                      "is_active": 1, "is_default": 1,
		                      "items": [{"item_code": k, "qty": v} for k, v in want.items()]})
		bom.flags.ignore_permissions = True
		bom.insert()
		bom.submit()
		new = bom.name
	if doc.meta.has_field("ren_recipe"):
		frappe.db.set_value("Item", doc.name, "ren_recipe", new)
	frappe.db.set_value("Item", doc.name, "default_bom", new)


@frappe.whitelist()
def search_ingredients(txt="", limit=20):
	"""Stock items to use in a recipe."""
	require_restaurant_user()
	access.require("edit_menu")
	txt = (txt or "").strip()
	or_filters = {"item_name": ["like", f"%{txt}%"], "name": ["like", f"%{txt}%"]} if txt else None
	return frappe.get_all("Item", filters={"disabled": 0, "is_stock_item": 1, "has_variants": 0},
	                      or_filters=or_filters, fields=["name as item_code", "item_name", "stock_uom as uom", "item_group"],
	                      order_by="item_name asc", limit=cint(limit) or 20)


# ─────────────────────────────────────────────
# Preview: the dialog the server will see, before saving
# ─────────────────────────────────────────────

@frappe.whitelist()
def preview(data, menu=None):
	"""
	Save the editor's data inside a savepoint, build what the POS would get
	for the item (its options and sizes) and roll back: nothing is kept.
	Invalid options fail here the same way they would on save.
	"""
	require_restaurant_user()
	access.require("edit_menu")
	data = _parse(data)
	frappe.db.savepoint("ren_item_preview")
	frappe.flags.ren_item_preview = True
	try:
		code = save_item(json.dumps({**data, "in_menu": None}), None)["item"]["item_code"]
		return _pos_view(code)
	finally:
		frappe.flags.ren_item_preview = False
		frappe.db.rollback(save_point="ren_item_preview")


def _pos_view(item_code):
	"""{item, modifier_groups, modifier_modes} as the order screen builds them (api/pos.py)."""
	from renpos.api import menus
	from renpos.api.modifiers import catalog_for_items, modes_for
	from renpos.api.pos import _with_variants
	price_list = _price_list()
	codes = [item_code] + frappe.get_all("Item", filters={"variant_of": item_code, "disabled": 0}, pluck="name")
	prices = menus.list_prices(codes, price_list)
	items = []
	for code in codes:
		row = frappe.db.get_value("Item", code, ["name as item_code", "item_name", "item_group", "has_variants",
		                                         "variant_of"], as_dict=True)
		row["price_list_rate"] = flt(prices.get(code))
		items.append(row)
	items = _with_variants(items)
	groups = catalog_for_items(items, price_list)
	from renpos.api.guards import current_restaurant
	return {"items": items, "modifier_groups": groups, "modifier_modes": modes_for(current_restaurant())}
