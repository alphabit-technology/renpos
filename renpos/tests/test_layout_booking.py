# -*- coding: utf-8 -*-
"""
Floor editor (ren.call) and booking API tests.

    bench --site <site> run-tests --module renpos.tests.test_layout_booking
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from renpos.api import booking as booking_api
from renpos.api import ren as ren_api
from renpos.tests.test_order_flow import (
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
        # Without "Ren Access Grant" rows (POS Profile > user > Restaurant
        # Permission) a user sees no tables: access is opt-in by design.
        from renpos.tests.test_order_flow import set_role
        frappe.set_user("Administrator")
        set_role(CASHIER2, "Server")  # a role without "every table"
        try:
            frappe.set_user(CASHIER2)
            res = ren_api.call("Ren Room", self.fx["room"], "get_tables", "{}")
            self.assertEqual(res["tables"], [])
        finally:
            frappe.set_user("Administrator")
            set_role(CASHIER2, "Cashier")
        frappe.set_user(CASHIER2)
        res = ren_api.call("Ren Room", self.fx["room"], "get_tables", "{}")
        self.assertIn(self.fx["table"], [t["name"] for t in res["tables"]])  # the cashier sees every table
        frappe.set_user(WAITER)
        # changing it is not
        self.assertRaises((frappe.PermissionError, frappe.ValidationError), ren_api.call,
                          "Ren Floor", self.fx["floor"], "add_room", "{}")
        self.assertRaises((frappe.PermissionError, frappe.ValidationError), ren_api.call,
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
        from renpos.ren_pos.doctype.ren_menu.ren_menu import (
            get_item_groups, get_items_for_tree,
        )
        frappe.set_user(WAITER)
        groups = [g["name"] for g in get_item_groups()]
        self.assertIn("Products", groups)
        items = get_items_for_tree(item_groups=json.dumps(["Products"]), search="_REN-")
        self.assertTrue(any(i["item_code"] == "_REN-BURGER" and i["price_list_rate"] == 10 for i in items))

    def test_waiter_bootstrap(self):
        from renpos.api.restaurant import init_restaurant
        from renpos.api.pos import get_pos_data
        from renpos.tests.test_order_flow import PROFILE
        frappe.set_user(WAITER)
        data = init_restaurant()
        self.assertEqual(data["_server"]["pos_profile"], PROFILE)
        self.assertTrue(data.get("floors"))
        pos = get_pos_data(PROFILE)
        self.assertTrue(any(i["item_code"] == "_REN-BURGER" for i in pos["items"]))


class TestNewObjectNames(FrappeTestCase):
    def test_new_centers_rooms_and_tables_get_free_names(self):
        from renpos.ren_pos.doctype.ren_base import next_free_description
        frappe.set_user("Administrator")
        fx = setup_fixtures()
        floor = frappe.get_doc("Ren Floor", fx["floor"])
        # another floor already has "S 1": a new center never repeats it
        other = frappe.get_doc({"doctype": "Ren Floor", "description": "_REN Other floor",
                                "restaurant": floor.restaurant}).insert(ignore_permissions=True)
        taken = next_free_description("Ren Station", "S ")
        frappe.get_doc({"doctype": "Ren Station", "description": taken, "floor": other.name}).insert(
            ignore_permissions=True)
        before = set(frappe.get_all("Ren Station", filters={"floor": fx["floor"]}, pluck="description"))
        floor.add_station()
        floor.add_station()
        new = set(frappe.get_all("Ren Station", filters={"floor": fx["floor"]}, pluck="description")) - before
        self.assertEqual(len(new), 2)
        self.assertNotIn(taken, new)
        # two floors may name a center the same way
        frappe.get_doc({"doctype": "Ren Station", "description": taken, "floor": fx["floor"]}).insert(
            ignore_permissions=True)
        room = frappe.get_doc("Ren Room", fx["room"])
        room.add_table()
        room.add_table()  # free names, never a random clash
        frappe.db.rollback()
