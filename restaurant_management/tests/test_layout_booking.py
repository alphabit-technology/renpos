# -*- coding: utf-8 -*-
"""
Floor editor (ren.call) and booking API tests.

    bench --site <site> run-tests --module restaurant_management.tests.test_layout_booking
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from restaurant_management.api import booking as booking_api
from restaurant_management.api import ren as ren_api
from restaurant_management.tests.test_order_flow import (
    MANAGER, WAITER, CASHIER2, CUSTOMER, setup_fixtures,
)


class TestLayoutAndBooking(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.fx = setup_fixtures()

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_floor_editor_as_manager(self):
        frappe.set_user(MANAGER)
        floor = self.fx["floor"]
        children = ren_api.call("Ren Floor", floor, "get_children", "{}")
        self.assertIn("rooms", children)
        before = len(children["rooms"])

        ren_api.call("Ren Floor", floor, "add_room", "{}")
        children = ren_api.call("Ren Floor", floor, "get_children", "{}")
        self.assertEqual(len(children["rooms"]), before + 1)

        new_room = children["rooms"][-1]["name"]
        ren_api.call("Ren Room", new_room, "add_table", "{}")
        tables = ren_api.call("Ren Room", new_room, "get_tables", "{}")["tables"]
        self.assertTrue(len(tables) >= 1)
        table = tables[0]["name"]

        ren_api.call("Ren Table", table, "set_attr", json.dumps({"attr": "shape", "value": "Round"}))
        self.assertEqual(frappe.db.get_value("Ren Table", table, "shape"), "Round")

        ren_api.call("Ren Table", table, "delete", "{}")
        self.assertFalse(frappe.db.exists("Ren Table", table))

    def test_waiter_cannot_edit_layout(self):
        frappe.set_user(WAITER)
        # reading the floor is fine
        ren_api.call("Ren Floor", self.fx["floor"], "get_children", "{}")
        # the waiter was granted the floor: sees its tables
        res = ren_api.call("Ren Room", self.fx["room"], "get_tables", "{}")
        self.assertIn(self.fx["table"], [t["name"] for t in res["tables"]])
        # Without "Restaurant Permission" rows (POS Profile > user > Restaurant
        # Permission) a user sees no tables: access is opt-in by design.
        frappe.set_user(CASHIER2)
        res = ren_api.call("Ren Room", self.fx["room"], "get_tables", "{}")
        self.assertEqual(res["tables"], [])
        # changing it is not
        self.assertRaises(frappe.PermissionError, ren_api.call,
                          "Ren Floor", self.fx["floor"], "add_room", "{}")
        self.assertRaises(frappe.PermissionError, ren_api.call,
                          "Ren Table", self.fx["table"], "delete", "{}")

    def test_booking_flow(self):
        frappe.set_user(WAITER)
        day = add_days(nowdate(), 1)
        avail = booking_api.get_table_availability(day, "19:00", "21:00", 2)
        mine = [t for t in avail if t["name"] == self.fx["table"]]
        self.assertTrue(mine and mine[0]["available"])
        self.assertEqual(mine[0]["room_name"], "Test room")

        res = booking_api.create_reservation(
            customer=CUSTOMER, customer_name=CUSTOMER, party_size=2,
            reservation_date=day, reservation_time="19:00", duration=120,
            table=self.fx["table"],
        )
        self.assertTrue(res["name"])

        avail = booking_api.get_table_availability(day, "19:30", "20:30", 2)
        mine = [t for t in avail if t["name"] == self.fx["table"]][0]
        self.assertFalse(mine["available"])

        found = booking_api.search_reservation(CUSTOMER[:6], date=day)
        self.assertTrue(any(b["name"] == res["name"] for b in found))

    def test_waiter_catalog(self):
        from restaurant_management.restaurant_management.doctype.restaurant_menu.restaurant_menu import (
            get_item_groups, get_items_for_tree,
        )
        frappe.set_user(WAITER)
        groups = [g["name"] for g in get_item_groups()]
        self.assertIn("Products", groups)
        items = get_items_for_tree(item_groups=json.dumps(["Products"]), search="_RM-")
        self.assertTrue(any(i["item_code"] == "_RM-BURGER" and i["price_list_rate"] == 10 for i in items))

    def test_waiter_bootstrap(self):
        from restaurant_management.api.restaurant import init_restaurant
        from restaurant_management.api.pos import get_pos_data
        from restaurant_management.tests.test_order_flow import PROFILE
        frappe.set_user(WAITER)
        data = init_restaurant()
        self.assertEqual(data["_server"]["pos_profile"], PROFILE)
        self.assertTrue(data.get("floors"))
        pos = get_pos_data(PROFILE)
        self.assertTrue(any(i["item_code"] == "_RM-BURGER" for i in pos["items"]))
