# -*- coding: utf-8 -*-
"""
Item options: set on the Item (sections + options, shared Option Lists),
components as items (nested, one level), sizes as ERPNext variants.
Server validation, price, texts, invoice and POS data.
Uses the fixtures of test_order_flow.
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from renpos.api import order as order_api
from renpos.api import pos as pos_api
from renpos.api import modifiers as mod_api
from renpos.tests.test_order_flow import (
	ITEM_A, ITEM_B, PROFILE, WAITER, open_register, setup_fixtures, _ensure_item,
)

ITEM_SIDE_STOCK = "_REN-FRIES-STOCK"
COOKING = "_REN Cooking"    # Ren Option List: required, pick 1
SIZE_ATTR = "_REN Cup Size"
DRINK = "_REN-DRINK"        # template: Small 2 / Large 3


# ─────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────

def _list(title, min_select, max_select, options, **rules):
	if frappe.db.exists("Ren Option List", title):
		frappe.delete_doc("Ren Option List", title, force=True, ignore_permissions=True)
	return frappe.get_doc({"doctype": "Ren Option List", "title": title, "min_select": min_select,
	                       "max_select": max_select, "options": options, **rules}).insert(ignore_permissions=True)


def set_options(item_code, options, sections=None, from_components=None):
	"""Item's Restaurant tab: options (rows) and sections (rules)."""
	doc = frappe.get_doc("Item", item_code)
	doc.set("ren_options", options)
	doc.set("ren_option_sections", sections or [])
	if from_components is not None:
		doc.ren_price_from_components = from_components
	doc.save(ignore_permissions=True)
	return doc


def opt(item_or_list, label):
	"""Option id by label (an Item's row or a Ren Option List's row)."""
	doctype = "Ren Option List" if frappe.db.exists("Ren Option List", item_or_list) else "Item"
	field = "options" if doctype == "Ren Option List" else "ren_options"
	return next(r.name for r in frappe.get_doc(doctype, item_or_list).get(field) if (r.label or r.item) == label)


def ensure_variants(template, prices, stock=0):
	"""Template with the size attribute and one variant per {value: price}."""
	from erpnext.controllers.item_variant import create_variant
	if not frappe.db.exists("Item Attribute", SIZE_ATTR):
		frappe.get_doc({"doctype": "Item Attribute", "attribute_name": SIZE_ATTR, "item_attribute_values": [
			{"attribute_value": "Small", "abbr": "S"}, {"attribute_value": "Medium", "abbr": "M"},
			{"attribute_value": "Large", "abbr": "L"}]}).insert(ignore_permissions=True)
	if not frappe.db.exists("Item", template):
		frappe.get_doc({"doctype": "Item", "item_code": template, "item_name": template, "item_group": "Products",
		                "stock_uom": "Nos", "is_stock_item": stock, "is_sales_item": 1, "has_variants": 1,
		                "attributes": [{"attribute": SIZE_ATTR}]}).insert(ignore_permissions=True)
	out = {}
	for value, price in prices.items():
		code = frappe.db.get_value("Item Variant Attribute", {"attribute": SIZE_ATTR, "attribute_value": value,
		                                                      "variant_of": template}, "parent")
		if not code:
			v = create_variant(template, {SIZE_ATTR: value})
			v.is_stock_item = stock
			v.insert(ignore_permissions=True)
			code = v.name
		_ensure_item(code, price)
		out[value] = code
	return out


def new_order(fx):
	frappe.set_user(WAITER)
	return order_api.add_order(fx["table"])["order"]["data"]["name"]


def push(order, item_code, chosen, qty=1, identifier=None):
	"""chosen: option ids, or dicts {option, qty, mode, parent}"""
	return order_api.push_item(order, json.dumps({
		"identifier": identifier or frappe.generate_hash(length=10),
		"item_code": item_code, "qty": qty, "price_list_rate": 999, "rate": 999,
		"discount_percentage": 0, "item_tax_rate": "{}",
		"modifiers": [c if isinstance(c, dict) else {"option": c} for c in chosen],
	}))["item"]


# ─────────────────────────────────────────────
# Options on the item, shared lists
# ─────────────────────────────────────────────

class TestItemOptions(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.fx = setup_fixtures()
		_ensure_item(ITEM_SIDE_STOCK, 1)
		_list(COOKING, 1, 1, [{"label": "Rare"}, {"label": "Medium", "preselected": 1}, {"label": "Well done"}])
		set_options(ITEM_A, [
			{"section": "Extras", "label": "Cheese", "price": 1.5},
			{"section": "Extras", "label": "Bacon", "price": 2},
			{"section": "Extras", "label": "Egg", "price": 1},
			{"section": "Extras", "label": "Truffle", "price": 9, "unavailable": 1},
		], sections=[
			{"section": "Cooking", "option_list": COOKING, "min_select": 1, "max_select": 1},
			{"section": "Extras", "max_select": 2},
		])

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		set_options(ITEM_A, [])
		super().tearDownClass()

	def tearDown(self):
		frappe.set_user("Administrator")

	def cook(self, label):
		return opt(COOKING, label)

	def extra(self, label):
		return opt(ITEM_A, label)

	# configuration
	def test_configuration_rules(self):
		self.assertRaises(frappe.ValidationError, _list, "_REN Bad", 2, 1, [{"label": "A"}, {"label": "B"}])
		self.assertRaises(frappe.ValidationError, _list, "_REN Bad", 2, 0, [{"label": "A"}])
		self.assertRaises(frappe.ValidationError, _list, "_REN Bad", 0, 1, [{"label": "A"}, {"label": "a"}])
		self.assertRaises(frappe.ValidationError, _list, "_REN Bad", 0, 0, [{"price": 1}])  # no item, no label
		self.assertRaises(frappe.ValidationError, set_options, ITEM_B, [{"label": "X"}],
		                  [{"section": "Empty"}])  # a section with nothing in it
		self.assertRaises(frappe.ValidationError, set_options, ITEM_B, [],
		                  [{"section": "A", "option_list": COOKING}, {"section": "B", "option_list": COOKING}])
		self.assertRaises(frappe.ValidationError, set_options, ITEM_B, [{"item": ITEM_B}])  # itself
		# a section with a Ren Option List takes its rules
		doc = set_options(ITEM_B, [], [{"section": "Cooking", "option_list": COOKING}])
		self.assertEqual((doc.ren_option_sections[0].min_select, doc.ren_option_sections[0].max_select), (1, 1))
		set_options(ITEM_B, [])

	def test_pos_data(self):
		frappe.set_user(WAITER)
		data = pos_api.get_pos_data(PROFILE)
		items = {i["item_code"]: i for i in data["items"]}
		self.assertEqual(items[ITEM_A]["modifier_groups"], [f"{ITEM_A}|Cooking", f"{ITEM_A}|Extras"])
		self.assertEqual(items[ITEM_B]["modifier_groups"], [])
		cooking = data["modifier_groups"][f"{ITEM_A}|Cooking"]
		self.assertEqual(([o["label"] for o in cooking["options"]], cooking["min_select"]),
		                 (["Rare", "Medium", "Well done"], 1))
		self.assertEqual([o["is_default"] for o in cooking["options"]], [0, 1, 0])
		labels = [o["label"] for o in data["modifier_groups"][f"{ITEM_A}|Extras"]["options"]]
		self.assertNotIn("Truffle", labels)  # unavailable (86) isn't offered

	# validation and price
	def test_price_includes_options(self):
		order = new_order(self.fx)
		item = push(order, ITEM_A, [self.cook("Rare"), self.extra("Cheese"), self.extra("Bacon")], qty=2)
		self.assertAlmostEqual(item["modifiers_amount"], 3.5)
		self.assertAlmostEqual(item["price_list_rate"], 13.5)   # 10 + 1.5 + 2, client value ignored
		self.assertAlmostEqual(item["amount"], 27)
		self.assertEqual(mod_api.texts(item["modifiers"]), ["Rare", "Cheese", "Bacon"])
		row = frappe.get_all("Ren Order Item", filters={"parent": order}, fields=["modifiers", "modifiers_amount"])[0]
		self.assertAlmostEqual(flt(row.modifiers_amount), 3.5)
		self.assertEqual(len(mod_api.parse(row.modifiers)), 3)

	def test_required_and_max_rules(self):
		order = new_order(self.fx)
		self.assertRaises(frappe.ValidationError, push, order, ITEM_A, [])  # cooking point is required
		self.assertRaises(frappe.ValidationError, push, order, ITEM_A, [self.cook("Rare"), self.cook("Medium")])
		self.assertRaises(frappe.ValidationError, push, order, ITEM_A,
		                  [self.cook("Rare")] + [self.extra(l) for l in ("Cheese", "Bacon", "Egg")])

	def test_foreign_or_unavailable_option_rejected(self):
		order = new_order(self.fx)
		self.assertRaises(frappe.ValidationError, push, order, ITEM_A, [self.cook("Rare"), self.extra("Truffle")])
		self.assertRaises(frappe.ValidationError, push, order, ITEM_B, [self.extra("Cheese")])  # B has no options

	def test_change_options_of_pending_line(self):
		order = new_order(self.fx)
		push(order, ITEM_A, [self.cook("Rare")], identifier="opt-edit-1")
		item = push(order, ITEM_A, [self.cook("Well done"), self.extra("Egg")], identifier="opt-edit-1")
		self.assertAlmostEqual(item["price_list_rate"], 11)
		rows = frappe.get_all("Ren Order Item", filters={"parent": order}, fields=["modifiers"])
		self.assertEqual(len(rows), 1)
		self.assertEqual(mod_api.texts(rows[0].modifiers), ["Well done", "Egg"])

	def test_invoice_and_description(self):
		frappe.set_user("Administrator")
		open_register(WAITER, self.fx["company"])
		order = new_order(self.fx)
		push(order, ITEM_A, [self.cook("Medium"), self.extra("Cheese")], qty=2)  # 2 x 11.5
		due = flt(order_api.get_payment_summary(order)["amount_due"])
		self.assertAlmostEqual(due, 23, places=2)
		res = order_api.process_payment(order, json.dumps([{"mode_of_payment": "Cash", "amount": due}]))
		inv = frappe.get_doc(res["invoice_doctype"], res["invoice"])
		self.assertEqual([r.item_code for r in inv.items], [ITEM_A])
		self.assertAlmostEqual(flt(inv.items[0].rate), 11.5)
		self.assertIn("Medium, Cheese", inv.items[0].description)

	def test_divide_keeps_options(self):
		order = new_order(self.fx)
		push(order, ITEM_A, [self.cook("Rare"), self.extra("Bacon")], qty=2, identifier="opt-div-1")
		res = order_api.divide_order(order, json.dumps({"opt-div-1": {"qty": 1}}))
		new = res["new_order"]["data"]["name"]
		row = frappe.get_all("Ren Order Item", filters={"parent": new}, fields=["modifiers", "price_list_rate"])[0]
		self.assertEqual(mod_api.texts(row.modifiers), ["Rare", "Bacon"])
		self.assertAlmostEqual(flt(row.price_list_rate), 12)

	def test_items_list_returns_parsed_options(self):
		order = new_order(self.fx)
		push(order, ITEM_A, [self.cook("Rare")])
		items = order_api.get_items(order)
		items = items.get("items", items) if isinstance(items, dict) else items
		self.assertEqual(items[0]["modifiers"][0]["label"], "Rare")

	def test_summary(self):
		self.assertEqual(mod_api.summary(json.dumps([{"label": "Rare"}, {"label": "Egg"}])), "Rare, Egg")
		self.assertEqual(mod_api.summary(None), "")


# ─────────────────────────────────────────────
# Included / optional components, price from components
# ─────────────────────────────────────────────

COMBO = "_REN-COMBO"            # fixed price 10
BUILD = "_REN-BUILD-BOWL"       # price from components (its price list price is ignored)


def combo_rows():
	return [
		{"role": "Included", "label": "Lettuce"},
		{"role": "Included", "label": "Tomato", "price": 0.5},
		{"label": "Cheese", "price": 1, "max_qty": 2},
		{"label": "Onion", "price": 0.75, "changes_price": 0},
		{"section": "Side", "role": "Included", "item": ITEM_SIDE_STOCK, "label": "Fries", "price": 3},
		{"section": "Side", "label": "Salad", "price": 4},
	]


class TestComponents(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.fx = setup_fixtures()
		_ensure_item(ITEM_SIDE_STOCK, 1)
		_ensure_item(COMBO, 10)
		_ensure_item(BUILD, 99)
		sections = [{"section": "Side", "min_select": 1, "max_select": 1}]
		set_options(COMBO, combo_rows(), sections)
		set_options(BUILD, combo_rows(), sections, from_components=1)

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		set_options(COMBO, [])
		set_options(BUILD, [], from_components=0)
		super().tearDownClass()

	def tearDown(self):
		frappe.set_user("Administrator")

	def push(self, item_code, chosen, qty=1):
		return push(new_order(self.fx), item_code,
		            [{"option": opt(item_code, l), "qty": q} for l, q in chosen], qty=qty)

	AS_IT_COMES = [("Lettuce", 1), ("Tomato", 1), ("Fries", 1)]

	def test_as_it_comes(self):
		item = self.push(COMBO, self.AS_IT_COMES)
		self.assertAlmostEqual(item["price_list_rate"], 10)
		self.assertEqual(mod_api.texts(item["modifiers"]), [])  # nothing changed: nothing to tell the kitchen

	def test_remove_add_and_swap(self):
		item = self.push(COMBO, [("Lettuce", 1), ("Cheese", 2), ("Onion", 1), ("Salad", 1)], qty=2)
		# 10 - tomato 0.5 + cheese 2 x 1 + onion (doesn't change the price) + salad 4 - fries 3
		self.assertAlmostEqual(item["modifiers_amount"], 2.5)
		self.assertAlmostEqual(item["price_list_rate"], 12.5)
		self.assertEqual(mod_api.texts(item["modifiers"]), ["NO Tomato", "Cheese x2", "Onion", "Salad (instead of Fries)"])

	def test_max_qty(self):
		self.assertRaises(frappe.ValidationError, self.push, COMBO, self.AS_IT_COMES + [("Cheese", 3)])

	def test_removals_come_from_the_server(self):
		order = new_order(self.fx)
		chosen = [{"option": opt(COMBO, l), "qty": q} for l, q in self.AS_IT_COMES]
		item = push(order, COMBO, chosen + [{"option": opt(COMBO, "Cheese"), "removed": 1, "price": -50}])
		self.assertAlmostEqual(item["price_list_rate"], 10)

	def test_price_from_components(self):
		frappe.set_user(WAITER)
		data = pos_api.get_pos_data(PROFILE)
		build = next(i for i in data["items"] if i["item_code"] == BUILD)
		self.assertEqual(build["price_from_components"], 1)
		self.assertAlmostEqual(build["price_list_rate"], 3.5)  # lettuce 0 + tomato 0.5 + fries 3
		self.assertAlmostEqual(self.push(BUILD, self.AS_IT_COMES)["price_list_rate"], 3.5)  # its own 99 is ignored
		self.assertAlmostEqual(self.push(BUILD, [("Cheese", 1), ("Salad", 1)])["price_list_rate"], 5)

	def test_included_options_start_checked(self):
		cat = mod_api.Catalog()
		names = cat.groups_for(COMBO)
		self.assertEqual([cat.groups[n]["title"] for n in names], ["Ingredients", "Side"])
		opts = {o["label"]: o for o in cat.groups[names[0]]["options"]}
		self.assertEqual((opts["Tomato"]["included"], opts["Tomato"]["is_default"]), (1, 1))
		self.assertEqual((opts["Cheese"]["included"], opts["Cheese"]["is_default"], opts["Cheese"]["max_qty"]), (0, 0, 2))
		self.assertEqual(opts["Onion"]["affects_price"], 0)


# ─────────────────────────────────────────────
# Modes, free choices, nested components and sizes
# ─────────────────────────────────────────────

RULES = "_REN-COMBO-RULES"   # 8
INNER = "_REN-INNER-BURGER"  # a dish with its own options, used inside a combo


class TestComboRules(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.fx = setup_fixtures()
		_ensure_item(ITEM_SIDE_STOCK, 1)
		_ensure_item(RULES, 8)
		_ensure_item(INNER, 7)
		cls.sizes = ensure_variants(DRINK, {"Small": 2, "Large": 3})
		mod_api.install_default_modes()
		cls.mode = {m["label"]: m["name"] for m in mod_api.modes_for()}
		_list("_REN Sauces", 0, 0, [{"label": "Ketchup", "price": 0.5}, {"label": "Mayo", "price": 0.5},
		                          {"label": "BBQ", "price": 0.75}], free_choices=2)
		set_options(INNER, [{"role": "Included", "label": "Pickles", "price": 0.25}])
		set_options(RULES, [
			{"section": "Parts", "role": "Included", "label": "Onion", "price": 0.25, "item": ITEM_SIDE_STOCK, "qty": 20},
			{"section": "Parts", "label": "Bacon", "price": 2},
			{"section": "Drink", "item": DRINK, "label": "Coke"},
			{"section": "Drink", "label": "Water"},
			{"section": "Main", "role": "Included", "item": INNER, "label": "Burger"},
		], sections=[
			{"section": "Sauces", "option_list": "_REN Sauces"},
			{"section": "Parts", "use_modes": 1},
			{"section": "Drink", "min_select": 1, "max_select": 1},
		])

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		set_options(RULES, [])
		set_options(INNER, [])
		super().tearDownClass()

	def tearDown(self):
		frappe.set_user("Administrator")

	def o(self, label):
		return opt(RULES, label)

	def burger(self):
		"""the burger as it comes (with its own included pickles, as the POS sends it)"""
		return [self.o("Burger"), {"option": opt(INNER, "Pickles"), "parent": self.o("Burger")}]

	def base(self):
		return [self.o("Onion"), self.o("Water")] + self.burger()

	def push(self, chosen):
		return push(new_order(self.fx), RULES, chosen)

	def test_free_choices(self):
		item = self.push(self.base() + [opt("_REN Sauces", l) for l in ("Ketchup", "Mayo", "BBQ")])
		self.assertAlmostEqual(item["modifiers_amount"], 0.75)  # the two cheapest are free
		self.assertAlmostEqual(item["price_list_rate"], 8.75)

	def test_ingredient_modes(self):
		water, burger = self.o("Water"), self.burger()
		item = self.push([{"option": self.o("Onion"), "mode": self.mode["Extra"]},
		                  {"option": self.o("Bacon"), "mode": self.mode["On the side"]}, water] + burger)
		self.assertAlmostEqual(item["price_list_rate"], 8 + 0.25 + 2)  # extra onion charged once more
		self.assertEqual(mod_api.texts(item["modifiers"]), ["EXTRA Onion", "Bacon ON THE SIDE", "Water"])
		onion = next(m for m in item["modifiers"] if m["label"] == "Onion")
		self.assertEqual((mod_api.portions(onion), onion["ingredient_qty"]), (2, 20))
		# modes only where the section offers them
		self.assertRaises(frappe.ValidationError, self.push,
		                  [self.o("Onion"), {"option": water, "mode": self.mode["Extra"]}] + burger)

	def test_component_with_sizes(self):
		coke = self.o("Coke")
		small, large = f"{DRINK}::{self.sizes['Small']}", f"{DRINK}::{self.sizes['Large']}"
		item = self.push([self.o("Onion"), coke, {"option": small, "parent": coke}] + self.burger())
		self.assertAlmostEqual(item["price_list_rate"], 8)  # the default (cheapest) size is included
		item = self.push([self.o("Onion"), coke, {"option": large, "parent": coke}] + self.burger())
		self.assertAlmostEqual(item["price_list_rate"], 9)  # bigger: the difference (3 - 2)
		self.assertEqual(mod_api.texts(item["modifiers"]), ["Coke: Large"])
		size = next(m for m in item["modifiers"] if m.get("parent") == coke)
		self.assertEqual((size["item"], size["variant"]), (self.sizes["Large"], 1))
		# the size is required once the drink is chosen
		self.assertRaises(frappe.ValidationError, self.push, [self.o("Onion"), coke] + self.burger())
		# a nested choice without its parent isn't accepted
		self.assertRaises(frappe.ValidationError, self.push, self.base() + [{"option": large, "parent": coke}])

	def test_component_with_its_own_options(self):
		burger = self.o("Burger")
		pickles = opt(INNER, "Pickles")
		# the burger as it comes: its pickles are sent as included
		item = self.push([self.o("Onion"), self.o("Water"), burger, {"option": pickles, "parent": burger}])
		self.assertEqual(mod_api.texts(item["modifiers"]), ["Water"])
		item = self.push([self.o("Onion"), self.o("Water"), burger])  # pickles removed inside the burger
		self.assertEqual(mod_api.texts(item["modifiers"]), ["Water", "Burger: NO Pickles"])
		self.assertAlmostEqual(item["price_list_rate"], 8 - 0.25)

	def test_pos_data(self):
		frappe.set_user(WAITER)
		data = pos_api.get_pos_data(PROFILE)
		groups = data["modifier_groups"]
		drink = groups[f"{RULES}|Drink"]
		coke = next(o for o in drink["options"] if o["label"] == "Coke")
		size = groups[coke["nested"][0]]
		self.assertEqual(([o["label"] for o in size["options"]], [o["price"] for o in size["options"]]),
		                 (["Small", "Large"], [0, 1]))
		burger = next(o for o in groups[f"{RULES}|Main"]["options"])
		self.assertEqual(burger["nested"], [f"{INNER}|"])
		self.assertTrue({"Light", "Extra", "On the side"} <= {m["label"] for m in data["modifier_modes"]})


# ─────────────────────────────────────────────
# Sizes of the item itself (ERPNext variants)
# ─────────────────────────────────────────────

class TestVariants(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.fx = setup_fixtures()
		cls.sizes = ensure_variants(DRINK, {"Small": 2, "Large": 3})
		set_options(DRINK, [{"section": "Ice", "label": "No ice"}])

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		set_options(DRINK, [])
		super().tearDownClass()

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_pos_shows_the_template_with_its_sizes(self):
		frappe.set_user(WAITER)
		data = pos_api.get_pos_data(PROFILE)
		items = {i["item_code"]: i for i in data["items"]}
		template = items[DRINK]
		self.assertEqual([v["label"] for v in template["variants"]["variants"]], ["Small", "Large"])
		self.assertEqual(template["variants"]["attributes"], [SIZE_ATTR])
		self.assertAlmostEqual(template["price_list_rate"], 2)  # from the cheapest
		large = items[self.sizes["Large"]]
		self.assertEqual(large["item_name"], f"{DRINK} Large")
		self.assertEqual(large["modifier_groups"], [f"{DRINK}|Ice"])  # the template's options

	def test_the_line_is_the_variant(self):
		order = new_order(self.fx)
		item = push(order, self.sizes["Large"], [opt(DRINK, "No ice")])
		self.assertAlmostEqual(item["price_list_rate"], 3)
		self.assertEqual(item["item_name"], f"{DRINK} Large")
		self.assertEqual(mod_api.texts(item["modifiers"]), ["No ice"])
		self.assertRaises(frappe.ValidationError, push, order, DRINK, [])  # the template is never sold

	def test_catalog_tree_shows_templates_only(self):
		from renpos.ren_pos.doctype.ren_menu.ren_menu import get_items_for_tree
		frappe.set_user(WAITER)
		items = {i["item_code"]: i for i in get_items_for_tree(search=DRINK, price_list="Standard Selling")}
		self.assertIn(DRINK, items)
		self.assertNotIn(self.sizes["Large"], items)
		self.assertAlmostEqual(items[DRINK]["price_list_rate"], 2)


PIZZA = "_REN-PIZZA"   # Small 10 (toppings x1) / Large 14 (toppings x1.5)


class TestPriceBySize(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.fx = setup_fixtures()
		cls.sizes = ensure_variants(PIZZA, {"Small": 10, "Large": 14})
		frappe.db.set_value("Item", cls.sizes["Large"], "ren_option_factor", 1.5)
		set_options(PIZZA, [
			{"section": "Toppings", "label": "Pepperoni", "price": 2},
			{"section": "Toppings", "label": "Olives", "price": 1},
			{"section": "Dip", "label": "Ranch", "price": 0.5},
		], [{"section": "Toppings", "price_by_size": 1}])

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		set_options(PIZZA, [])
		super().tearDownClass()

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_toppings_cost_more_on_a_large(self):
		order = new_order(self.fx)
		chosen = [opt(PIZZA, "Pepperoni"), opt(PIZZA, "Ranch")]
		self.assertAlmostEqual(push(order, self.sizes["Small"], chosen)["price_list_rate"], 12.5)
		self.assertAlmostEqual(push(order, self.sizes["Large"], chosen)["price_list_rate"], 14 + 3 + 0.5)  # dip stays

	def test_pos_data_has_a_priced_section_per_size(self):
		frappe.set_user(WAITER)
		data = pos_api.get_pos_data(PROFILE)
		items = {i["item_code"]: i for i in data["items"]}
		small, large = items[self.sizes["Small"]], items[self.sizes["Large"]]
		self.assertEqual(small["modifier_groups"][0], f"{PIZZA}|Toppings")
		key = large["modifier_groups"][0]
		self.assertEqual(key, f"{PIZZA}|Toppings@{self.sizes['Large']}")
		group = data["modifier_groups"][key]
		self.assertEqual(group["name"], f"{PIZZA}|Toppings")  # same name: choices survive a size change
		self.assertEqual([o["price"] for o in group["options"]], [3, 1.5])
		self.assertEqual(large["modifier_groups"][1], f"{PIZZA}|Dip")
