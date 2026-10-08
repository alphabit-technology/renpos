# -*- coding: utf-8 -*-
"""Menus: which menu is in force, menu prices, sold out (86), menu-only selling, catalog order."""

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from renpos.api import menus
from renpos.api import order as order_api
from renpos.ren_pos.doctype.ren_menu.ren_menu import (
    get_item_groups, get_items_for_tree,
)
from renpos.tests.test_order_flow import (
    ITEM_A, ITEM_B, MANAGER, RESTAURANT, WAITER, setup_fixtures,
)


def make_menu(name, company, items, enabled=1):
    if frappe.db.exists("Ren Menu", name):
        frappe.delete_doc("Ren Menu", name, force=True, ignore_permissions=True)
    return frappe.get_doc({
        "doctype": "Ren Menu", "menu_name": name, "company": company, "enabled": enabled,
        "items": [{"item": code, "enabled": 1, "rate": rate} for code, rate in items],
    }).insert(ignore_permissions=True).name


class TestMenus(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.fx = setup_fixtures()
        cls.company = frappe.db.get_value("Ren Restaurant", RESTAURANT, "company") or cls.fx["company"]
        frappe.db.set_value("Ren Restaurant", RESTAURANT, "company", cls.company)
        cls.saved = {
            "active": frappe.db.get_value("Ren Restaurant", RESTAURANT, "active_menu"),
            "room": frappe.db.get_value("Ren Room", cls.fx["room"], "menu"),
        }
        # B first, A second; A costs 7 on this menu (price list: 10)
        cls.main = make_menu("_REN Main", cls.company, [(ITEM_B, 0), (ITEM_A, 7)])
        cls.bar = make_menu("_REN Bar", cls.company, [(ITEM_B, 0)])

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        frappe.db.set_value("Ren Restaurant", RESTAURANT, "active_menu", cls.saved["active"])
        frappe.db.set_value("Ren Room", cls.fx["room"], "menu", cls.saved["room"])
        for m in (cls.main, cls.bar):
            frappe.delete_doc("Ren Menu", m, force=True, ignore_permissions=True)
        frappe.db.delete("Ren Sold Out", {"restaurant": RESTAURANT})
        frappe.db.set_single_value("Ren Settings", "only_menu_items", 0)
        super().tearDownClass()

    def setUp(self):
        frappe.set_user("Administrator")
        frappe.db.set_value("Ren Room", self.fx["room"], "menu", None)
        menus.set_active_menu(self.main, RESTAURANT)
        frappe.db.delete("Ren Sold Out", {"restaurant": RESTAURANT})
        frappe.db.set_single_value("Ren Settings", "only_menu_items", 0)

    def tearDown(self):
        frappe.set_user("Administrator")

    def new_order(self):
        frappe.set_user(WAITER)
        return order_api.add_order(self.fx["table"])["order"]["data"]["name"]

    def push(self, order, code, ident):
        return order_api.push_item(order, json.dumps({
            "identifier": ident, "item_code": code, "qty": 1, "price_list_rate": 0, "rate": 0,
            "discount_percentage": 0, "item_tax_rate": "{}"}))

    def test_menu_in_force(self):
        self.assertEqual(menus.resolve_menu(room=self.fx["room"])["source"], "restaurant")
        frappe.db.set_value("Ren Room", self.fx["room"], "menu", self.bar)
        m = menus.resolve_menu(room=self.fx["room"])
        self.assertEqual((m["name"], m["source"]), (self.bar, "room"))
        # a disabled room menu falls back to the restaurant's
        frappe.db.set_value("Ren Menu", self.bar, "enabled", 0)
        self.assertEqual(menus.resolve_menu(room=self.fx["room"])["name"], self.main)
        frappe.db.set_value("Ren Menu", self.bar, "enabled", 1)
        # the star moves the restaurant and the company default together
        menus.set_active_menu(self.bar, RESTAURANT)
        self.assertEqual(frappe.db.get_value("Ren Restaurant", RESTAURANT, "active_menu"), self.bar)
        self.assertEqual(frappe.db.get_value("Ren Menu", self.main, "is_default"), 0)
        listed = {m["name"]: m for m in menus.list_menus(company=self.company, restaurant=RESTAURANT)["menus"]}
        self.assertEqual(listed[self.bar]["is_active"], 1)

    def test_catalog_order_groups_and_menu_price(self):
        frappe.set_user(WAITER)
        items = get_items_for_tree(menu_name=self.main)
        self.assertEqual([i["item_code"] for i in items], [ITEM_B, ITEM_A])  # the menu's order
        prices = {i["item_code"]: i["price_list_rate"] for i in items}
        self.assertEqual((prices[ITEM_A], prices[ITEM_B]), (7, 2.5))
        groups = [g["name"] for g in get_item_groups(self.main)]
        self.assertIn("Products", groups)
        self.assertLess(len(groups), len(get_item_groups()))
        # the order charges the same menu price
        order = self.new_order()
        res = self.push(order, ITEM_A, "m-a")
        self.assertEqual(res["item"]["price_list_rate"], 7)
        # a disabled menu shows nothing
        frappe.set_user("Administrator")
        frappe.db.set_value("Ren Menu", self.bar, "enabled", 0)
        frappe.set_user(WAITER)
        self.assertEqual(get_items_for_tree(menu_name=self.bar), [])
        frappe.set_user("Administrator")
        frappe.db.set_value("Ren Menu", self.bar, "enabled", 1)

    def test_sold_out(self):
        frappe.set_user(WAITER)
        order = self.new_order()
        self.push(order, ITEM_B, "so-1")  # already on the order before it ran out
        menus.set_sold_out(ITEM_B, 1)
        items = {i["item_code"]: i for i in get_items_for_tree(menu_name=self.main)}
        self.assertFalse(items[ITEM_B]["is_available"])
        self.assertTrue(items[ITEM_A]["is_available"])
        self.assertRaises(frappe.ValidationError, self.push, order, ITEM_B, "so-2")
        # lines already taken can still be changed
        order_api.push_item(order, json.dumps({"identifier": "so-1", "item_code": ITEM_B, "qty": 2,
                                                "price_list_rate": 2.5, "rate": 2.5, "discount_percentage": 0,
                                                "item_tax_rate": "{}"}))
        menus.set_sold_out(ITEM_B, 0)
        self.push(order, ITEM_B, "so-3")

    def test_only_menu_items(self):
        frappe.set_user("Administrator")
        frappe.db.set_value("Ren Room", self.fx["room"], "menu", self.bar)  # bar: only B
        order = self.new_order()
        self.push(order, ITEM_A, "om-1")  # allowed while the setting is off
        frappe.set_user("Administrator")
        frappe.db.set_single_value("Ren Settings", "only_menu_items", 1)
        frappe.set_user(WAITER)
        self.assertRaises(frappe.ValidationError, self.push, order, ITEM_A, "om-2")
        self.push(order, ITEM_B, "om-3")

    def test_set_menu_item(self):
        frappe.set_user(MANAGER)
        menus.set_menu_item(self.bar, ITEM_A, 1, rate=3)
        row = frappe.db.get_value("Ren Menu Item", {"parent": self.bar, "item": ITEM_A}, ["enabled", "rate"],
                                  as_dict=True)
        self.assertEqual((row.enabled, row.rate), (1, 3))
        frappe.db.set_value("Ren Menu Item", {"parent": self.bar, "item": ITEM_A}, "enabled", 0)
        menus.set_menu_item(self.bar, ITEM_A, 1)  # a disabled row comes back
        self.assertEqual(frappe.db.get_value("Ren Menu Item", {"parent": self.bar, "item": ITEM_A}, "enabled"), 1)
        menus.set_menu_item(self.bar, ITEM_A, 0)
        self.assertFalse(frappe.db.exists("Ren Menu Item", {"parent": self.bar, "item": ITEM_A}))

    def test_legacy_menu_rows_can_be_removed(self):
        """Rows saved under the old `menu_items` field are moved to `items` and can be taken off."""
        from renpos.patches.v2_0 import menu_items_parentfield
        from renpos.ren_pos.doctype.ren_menu.ren_menu import (
            get_menu_item_codes,
        )
        frappe.set_user("Administrator")
        legacy = frappe.get_doc({"doctype": "Ren Menu Item", "parenttype": "Ren Menu",
                                 "parent": self.bar, "parentfield": "menu_items", "item": ITEM_A, "enabled": 1})
        legacy.db_insert()
        dup = frappe.get_doc({"doctype": "Ren Menu Item", "parenttype": "Ren Menu",
                              "parent": self.bar, "parentfield": "menu_items", "item": ITEM_B, "enabled": 1})
        dup.db_insert()  # ITEM_B is already on the menu: the legacy copy goes away
        menu_items_parentfield.execute()
        self.assertEqual(frappe.db.count("Ren Menu Item", {"parent": self.bar, "item": ITEM_B}), 1)
        self.assertEqual(frappe.db.get_value("Ren Menu", self.bar, "total_items"), 2)

        frappe.set_user(MANAGER)
        menus.set_menu_item(self.bar, ITEM_A, 0)
        self.assertNotIn(ITEM_A, get_menu_item_codes(self.bar))

    def test_scheduled_menu_and_tags(self):
        from datetime import datetime
        frappe.set_user("Administrator")
        doc = frappe.get_doc("Ren Menu", self.bar)
        doc.set("schedule", [{"weekday": "Every day", "from_time": "16:00", "to_time": "18:00"}])
        doc.save()
        try:
            at = datetime(2026, 10, 2, 17, 0)
            self.assertEqual(menus.resolve_menu(restaurant=RESTAURANT, at=at)["source"], "schedule")
            self.assertEqual(menus.resolve_menu(restaurant=RESTAURANT, at=datetime(2026, 10, 2, 19, 0))["name"],
                             self.main)
            # a room menu still wins
            frappe.db.set_value("Ren Room", self.fx["room"], "menu", self.main)
            self.assertEqual(menus.resolve_menu(room=self.fx["room"], at=at)["source"], "room")
        finally:
            doc.reload()
            doc.set("schedule", [])
            doc.save()
        # tags: filter and show
        menus.install_default_tags()
        item = frappe.get_doc("Item", ITEM_B)
        item.set("ren_tags", [{"tag": "Vegan"}])
        item.save(ignore_permissions=True)
        frappe.set_user(WAITER)
        tagged = get_items_for_tree(menu_name=self.main, tag="Vegan")
        self.assertEqual([i["item_code"] for i in tagged], [ITEM_B])
        self.assertEqual(tagged[0]["tags"], ["Vegan"])
        self.assertTrue(any(t["name"] == "Vegan" for t in menus.get_menu_tags()))
