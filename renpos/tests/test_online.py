# -*- coding: utf-8 -*-
"""Guests order from their phones: pickup online and QR at the table (api/online.py)."""

import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, flt, now_datetime

from renpos.api import online
from renpos.api import order as order_api
from renpos.tests.test_menus import make_menu
from renpos.tests.test_order_flow import (
    ITEM_A, ITEM_B, RESTAURANT, WAITER, setup_fixtures,
)

MENU = "_REN Online Menu"
HIDDEN = "_REN-NOT-ON-MENU"


class TestOnlineOrdering(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.fx = setup_fixtures()
        from renpos.tests.test_order_flow import _ensure_item
        _ensure_item(HIDDEN, 4)
        company = cls.fx["company"]
        cls.menu = make_menu(MENU, company, [(ITEM_A, 0), (ITEM_B, 3)])  # the soda is 3.00 on this menu
        cls.old_menu = frappe.db.get_value("Ren Room", cls.fx["room"], "menu")
        frappe.db.set_value("Ren Room", cls.fx["room"], "menu", cls.menu)
        pickup = frappe.db.get_value("Ren Table", {"room": cls.fx["room"], "description": "Pickup"})
        if not pickup:
            pickup = frappe.get_doc({"doctype": "Ren Table", "room": cls.fx["room"], "description": "Pickup",
                                     "no_of_seats": 1}).insert(ignore_permissions=True).name
        cls.pickup = pickup
        frappe.db.set_value("Ren Restaurant", RESTAURANT, {
            "online_ordering": 1, "pickup_table": pickup, "pickup_prep_minutes": 20,
            "table_ordering": 1, "table_orders_to_kitchen": 0})
        frappe.db.delete("Ren Sold Out", {"restaurant": RESTAURANT})
        cls.token = online.ensure_token(cls.fx["table"])

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        super().tearDownClass()
        frappe.db.set_value("Ren Room", cls.fx["room"], "menu", cls.old_menu)
        frappe.db.set_value("Ren Restaurant", RESTAURANT, {"online_ordering": 0, "table_ordering": 0})
        frappe.db.commit()

    def setUp(self):
        frappe.set_user("Guest")
        frappe.local.request_ip = "127.0.0.1"
        # a clean table each time
        frappe.set_user("Administrator")
        for name in frappe.get_all("Ren Order", filters={"table": ["in", [self.fx["table"], self.pickup]],
                                                           "status": ["not in", ["Invoiced"]]}, pluck="name"):
            frappe.flags.ren_order_api = True
            frappe.delete_doc("Ren Order", name, force=True, ignore_permissions=True)
        frappe.set_user("Guest")

    def tearDown(self):
        frappe.set_user("Administrator")

    def lines(self, order_name):
        return frappe.get_all("Ren Order Item", filters={"parent": order_name, "parenttype": "Ren Order"},
                              fields=["item_code", "qty", "rate", "status", "ren_hold", "notes"], order_by="idx")

    def test_menu_shows_only_the_menu_at_its_prices(self):
        m = online.menu(r=RESTAURANT)
        self.assertEqual(m["mode"], "pickup")
        codes = {i["item_code"]: i for i in m["items"]}
        self.assertIn(ITEM_A, codes)
        self.assertNotIn(HIDDEN, codes)
        self.assertEqual(flt(codes[ITEM_B]["price_list_rate"]), 3)
        self.assertTrue(m["slots"])
        # sold out disappears
        frappe.set_user("Administrator")
        frappe.get_doc({"doctype": "Ren Sold Out", "restaurant": RESTAURANT, "item_code": ITEM_B}).insert(
            ignore_permissions=True)
        frappe.set_user("Guest")
        self.assertNotIn(ITEM_B, {i["item_code"] for i in online.menu(r=RESTAURANT)["items"]})
        frappe.db.delete("Ren Sold Out", {"restaurant": RESTAURANT})

    def test_pickup_asap_goes_to_the_kitchen_at_server_prices(self):
        res = online.place(json.dumps([
            {"item_code": ITEM_A, "qty": 2, "price_list_rate": 0.01, "rate": 0.01, "discount_percentage": 100},
            {"item_code": ITEM_B, "qty": 1, "notes": "<b>no ice</b>"},
        ]), r=RESTAURANT, guest_name="Ana", phone="(555) 123-4567")
        self.assertEqual(res["state"], "preparing")
        name = frappe.db.get_value("Ren Order", {"ren_guest_token": res["token"]}, "name")
        order = frappe.get_doc("Ren Order", name)
        self.assertEqual((order.table, order.ren_origin, order.ren_guest_name, order.owner),
                         (self.pickup, "Online", "Ana", "Guest"))
        lines = self.lines(name)
        self.assertEqual([(l.item_code, flt(l.rate), l.status) for l in lines],
                         [(ITEM_A, 10, "Sent"), (ITEM_B, 3, "Sent")])  # never the client's price
        self.assertNotIn("<b>", lines[1].notes)
        self.assertEqual(online.status(res["token"])["state"], "preparing")

        # every server sees and works the guest's order
        frappe.set_user(WAITER)
        got = order_api.get_orders(self.pickup)
        self.assertIn(name, [o["data"]["name"] for o in got["orders"]])
        order_api.get_items(name)

    def test_pickup_later_is_held_then_fired(self):
        prep, slots = online.pickup_slots(RESTAURANT)
        later = slots[-1]
        res = online.place(json.dumps([{"item_code": ITEM_A, "qty": 1}]), r=RESTAURANT,
                           guest_name="Bo", phone="5551234567", pickup_at=later)
        self.assertEqual(res["state"], "scheduled")
        name = frappe.db.get_value("Ren Order", {"ren_guest_token": res["token"]}, "name")
        self.assertEqual(self.lines(name)[0].ren_hold, 1)
        frappe.set_user("Administrator")
        online.fire_due_pickups()
        self.assertEqual(self.lines(name)[0].status, "Pending")  # not yet
        frappe.db.set_value("Ren Order", name, "ren_pickup_time", add_to_date(now_datetime(), minutes=10))
        online.fire_due_pickups()
        self.assertEqual((self.lines(name)[0].status, self.lines(name)[0].ren_hold), ("Sent", 0))

    def test_pickup_needs_name_phone_and_a_valid_time(self):
        items = json.dumps([{"item_code": ITEM_A, "qty": 1}])
        self.assertRaises(frappe.ValidationError, online.place, items, r=RESTAURANT, guest_name="", phone="555")
        self.assertRaises(frappe.ValidationError, online.place, items, r=RESTAURANT, guest_name="Al",
                          phone="5551234567", pickup_at=str(now_datetime()))
        self.assertRaises(frappe.ValidationError, online.place, json.dumps([{"item_code": HIDDEN, "qty": 1}]),
                          r=RESTAURANT, guest_name="Al", phone="5551234567")
        self.assertRaises(frappe.ValidationError, online.place, json.dumps([{"item_code": ITEM_A, "qty": 0}]),
                          r=RESTAURANT, guest_name="Al", phone="5551234567")

    def test_table_order_waits_for_the_server_and_joins_the_open_order(self):
        res = online.place(json.dumps([{"item_code": ITEM_A, "qty": 1}]), t=self.token)
        self.assertEqual(res["state"], "received")
        name = frappe.db.get_value("Ren Order", {"ren_guest_token": res["token"]}, "name")
        self.assertEqual(frappe.db.get_value("Ren Order", name, ["table", "ren_origin"]),
                         (self.fx["table"], "Table QR"))
        self.assertEqual(self.lines(name)[0].status, "Pending")
        # a second round from the same table goes to the same order
        res2 = online.place(json.dumps([{"item_code": ITEM_B, "qty": 2}]), t=self.token)
        self.assertEqual(res2["token"], res["token"])
        self.assertEqual(len(self.lines(name)), 2)

        # the server sends it
        frappe.set_user(WAITER)
        order_api.send_order(name)
        frappe.set_user("Guest")
        self.assertEqual(online.status(res["token"])["state"], "preparing")

    def test_table_order_straight_to_the_kitchen_sends_only_the_guests_lines(self):
        frappe.set_user(WAITER)
        order = order_api.add_order(self.fx["table"])["order"]["data"]["name"]
        order_api.push_item(order, json.dumps({"identifier": "w-" + frappe.generate_hash(length=6),
                                               "item_code": ITEM_A, "qty": 1, "price_list_rate": 10, "rate": 10,
                                               "discount_percentage": 0, "item_tax_rate": "{}"}))
        frappe.set_user("Administrator")
        frappe.db.set_value("Ren Restaurant", RESTAURANT, "table_orders_to_kitchen", 1)
        try:
            frappe.set_user("Guest")
            online.place(json.dumps([{"item_code": ITEM_B, "qty": 1}]), t=self.token)
            statuses = {(l.item_code, l.status) for l in self.lines(order)}
            self.assertEqual(statuses, {(ITEM_A, "Pending"), (ITEM_B, "Sent")})
        finally:
            frappe.db.set_value("Ren Restaurant", RESTAURANT, "table_orders_to_kitchen", 0)

    def test_closed_ordering_and_bad_codes(self):
        self.assertRaises(frappe.ValidationError, online.menu, t="nope")
        frappe.db.set_value("Ren Restaurant", RESTAURANT, "table_ordering", 0)
        try:
            self.assertRaises(frappe.ValidationError, online.menu, t=self.token)
        finally:
            frappe.db.set_value("Ren Restaurant", RESTAURANT, "table_ordering", 1)
        self.assertRaises(frappe.ValidationError, online.status, "x" * 24)

    def test_qr_codes_for_managers(self):
        self.assertRaises(frappe.PermissionError, online.table_qr_codes, RESTAURANT)
        frappe.set_user("Administrator")
        codes = online.table_qr_codes(RESTAURANT)
        row = next(c for c in codes if c["table"] == self.fx["table"])
        self.assertTrue(row["url"].endswith(f"/order?t={self.token}"))
        self.assertIn("<svg", row["svg"])
