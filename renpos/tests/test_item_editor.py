# -*- coding: utf-8 -*-
"""The Menu Manager's item editor writes the ERPNext Item itself (api/item_editor.py)."""

import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from renpos.api import item_editor as ed
from renpos.tests.test_menus import make_menu
from renpos.tests.test_order_flow import ITEM_A, ITEM_B, WAITER, setup_fixtures


class TestItemEditor(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.fx = setup_fixtures()
        cls.menu = make_menu("_REN Editor Menu", cls.fx["company"], [(ITEM_A, 0)])

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_new_combo_on_the_menu(self):
        frappe.set_user("Administrator")
        res = ed.save_item(json.dumps({
            "item_name": "_REN Editor Combo", "item_group": "Products", "price": 11.5,
            "route_components": 1,
            "sections": [{"section": "Burger", "min_select": 1, "max_select": 1},
                         {"section": "Drink", "min_select": 1, "max_select": 1}],
            "options": [{"section": "Burger", "role": "Included", "item": ITEM_A},
                        {"section": "Drink", "role": "Included", "item": ITEM_B},
                        {"section": "Drink", "role": "Optional", "label": "  "}],  # empty rows are dropped
            "in_menu": 1, "menu_rate": 9.99,
        }), menu=self.menu)
        code = res["item"]["item_code"]
        item = frappe.get_doc("Item", code)
        self.assertEqual((item.item_name, item.is_sales_item, item.is_stock_item, item.ren_route_components),
                         ("_REN Editor Combo", 1, 0, 1))
        self.assertEqual([o.item for o in item.ren_options], [ITEM_A, ITEM_B])
        self.assertEqual(res["item"]["price"], 11.5)
        self.assertEqual(res["menu"], {"name": self.menu, "in_menu": True, "rate": 9.99})

        # edit: new price, off the menu
        data = res["item"] | {"price": 12, "in_menu": 0}
        res = ed.save_item(json.dumps(data), menu=self.menu)
        self.assertEqual(flt(res["item"]["price"]), 12)
        self.assertFalse(res["menu"]["in_menu"])
        self.assertEqual(frappe.db.count("Item Price", {"item_code": code}), 1)

    def test_invalid_options_are_refused(self):
        frappe.set_user("Administrator")
        self.assertRaises(frappe.ValidationError, ed.save_item, json.dumps({
            "item_name": "_REN Editor Bad", "item_group": "Products",
            "sections": [{"section": "Empty", "min_select": 1}], "options": []}))

    def test_waiters_cant_edit(self):
        frappe.set_user(WAITER)
        self.assertRaises(Exception, ed.get_item, ITEM_A)

    def test_new_item_with_sizes_and_a_recipe(self):
        frappe.set_user("Administrator")
        ing = frappe.get_all("Item", filters={"is_stock_item": 1, "has_variants": 0, "disabled": 0}, pluck="name", limit=1)
        res = ed.save_item(json.dumps({
            "item_name": "_REN Editor Shake", "item_group": "Products",
            "sizes": {"attribute": "_REN Shake Size", "values": [
                {"value": "Regular", "price": 5}, {"value": "Big", "price": 7}]},
            "recipe": [{"item_code": ing[0], "qty": 2}] if ing else [],
        }))
        sizes = res["item"]["sizes"] if "sizes" in res["item"] else res["sizes"]
        self.assertEqual([(v["value"], v["price"]) for v in sizes["values"]], [("Regular", 5), ("Big", 7)])
        if ing:
            self.assertEqual([(l["item_code"], l["qty"]) for l in res["recipe"]["lines"]], [(ing[0], 2)])
            # a different recipe replaces the BOM, the old one is no longer active
            old = res["recipe"]["bom"]
            res = ed.save_item(json.dumps(res["item"] | {"recipe": [{"item_code": ing[0], "qty": 3}]}))
            self.assertNotEqual(res["recipe"]["bom"], old)
            self.assertEqual(frappe.db.get_value("BOM", old, "is_active"), 0)

        # one more size later, one turned off
        res = ed.save_item(json.dumps(res["item"] | {"sizes": {"attribute": "_REN Shake Size", "values": [
            {"value": "Regular", "price": 5, "enabled": 0}, {"value": "Big", "price": 7.5}, {"value": "Kids", "price": 3}]}}))
        got = {v["value"]: (v["price"], v["enabled"]) for v in res["sizes"]["values"]}
        self.assertEqual(got, {"Regular": (5, False), "Big": (7.5, True), "Kids": (3, True)})

    def test_a_sold_item_cant_become_sizes(self):
        frappe.set_user("Administrator")
        frappe.db.delete("Ren Order Item", {"item_code": "_REN-NOPE"})  # nothing
        sold = frappe.db.get_value("Ren Order Item", {"item_code": ITEM_A}, "name") or \
            frappe.db.get_value("Sales Invoice Item", {"item_code": ITEM_A}, "name")
        if not sold:
            return
        data = ed.get_item(ITEM_A)["item"] | {"sizes": {"attribute": "Size", "values": [{"value": "Small", "price": 1}]}}
        self.assertRaises(frappe.ValidationError, ed.save_item, json.dumps(data))

    def test_preview_keeps_nothing(self):
        frappe.set_user("Administrator")
        before = frappe.db.count("Item")
        view = ed.preview(json.dumps({
            "item_name": "_REN Editor Preview", "item_group": "Products", "price": 4,
            "sections": [{"section": "Drink", "min_select": 1, "max_select": 1}],
            "options": [{"section": "Drink", "role": "Optional", "item": ITEM_B}],
        }))
        self.assertEqual(frappe.db.count("Item"), before)
        item = view["items"][0]
        self.assertEqual(item["price_list_rate"], 4)
        groups = [view["modifier_groups"][g] for g in item["modifier_groups"]]
        self.assertEqual([g["title"] for g in groups], ["Drink"])
        self.assertRaises(frappe.ValidationError, ed.preview, json.dumps({
            "item_name": "_REN Editor Preview", "item_group": "Products",
            "sections": [{"section": "Empty", "min_select": 1}], "options": []}))
