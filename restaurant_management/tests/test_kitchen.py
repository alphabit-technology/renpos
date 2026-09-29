# -*- coding: utf-8 -*-
"""
Kitchen display API tests.

    bench --site <site> run-tests --module restaurant_management.tests.test_kitchen
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from restaurant_management.api import kitchen as kitchen_api
from restaurant_management.api import order as order_api
from restaurant_management.tests.test_order_flow import (
    WAITER, ITEM_A, ITEM_B, setup_fixtures,
)


def make_station(floor, name="_RM Kitchen"):
    existing = frappe.db.get_value("Ren Station", {"description": name})
    if existing:
        return existing
    return frappe.get_doc({
        "doctype": "Ren Station",
        "description": name,
        "floor": floor,
        "production_center_group": [{"item_group": "Products"}],
        "status_managed": [
            {"status_managed": "Sent", "next_status": "Processing"},
            {"status_managed": "Processing", "next_status": "Completed"},
        ],
    }).insert(ignore_permissions=True).name


class TestKitchen(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.fx = setup_fixtures()
        cls.station = make_station(cls.fx["floor"])

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_queue_and_advance(self):
        frappe.set_user(WAITER)
        order = order_api.add_order(self.fx["table"])["order"]["data"]["name"]
        for code, ident in ((ITEM_A, "k-a"), (ITEM_B, "k-b")):
            order_api.push_item(order, json.dumps({
                "identifier": ident, "item_code": code, "qty": 1,
                "price_list_rate": 0, "discount_percentage": 0, "rate": 0, "item_tax_rate": "{}",
            }))

        # nothing in the kitchen until the order is sent
        q = kitchen_api.get_station_queue(self.station)
        self.assertFalse(any(t["order"] == order for t in q["tickets"]))

        order_api.send_order(order)
        q = kitchen_api.get_station_queue(self.station)
        ticket = [t for t in q["tickets"] if t["order"] == order][0]
        self.assertEqual({i["identifier"] for i in ticket["items"]}, {"k-a", "k-b"})
        self.assertEqual(ticket["items"][0]["status"], "Sent")
        self.assertEqual(ticket["items"][0]["next_status"], "Processing")
        self.assertEqual(ticket["table"], self.fx["table"])

        self.assertEqual(kitchen_api.advance(self.station, "k-a")["status"], "Processing")
        self.assertEqual(kitchen_api.advance(self.station, "k-a")["status"], "Completed")
        # completed items leave the queue and can't advance further
        q = kitchen_api.get_station_queue(self.station)
        ticket = [t for t in q["tickets"] if t["order"] == order][0]
        self.assertEqual([i["identifier"] for i in ticket["items"]], ["k-b"])
        self.assertRaises(frappe.ValidationError, kitchen_api.advance, self.station, "k-a")

        # the waiter's order shows the kitchen status
        items = {i["identifier"]: i for i in order_api.get_items(order)["items"]}
        self.assertEqual(items["k-a"]["status"], "Completed")

    def test_stations_listed(self):
        frappe.set_user(WAITER)
        names = [s["name"] for s in kitchen_api.get_stations()]
        self.assertIn(self.station, names)

    def test_grouped_station_sees_sent_orders(self):
        frappe.set_user("Administrator")
        grouped = make_station(self.fx["floor"], name="_RM Grill (grouped)")
        frappe.db.set_value("Ren Station", grouped, "group_items_by_order", 1)
        frappe.set_user(WAITER)
        order = order_api.add_order(self.fx["table"])["order"]["data"]["name"]
        order_api.push_item(order, json.dumps({
            "identifier": "g-a", "item_code": ITEM_A, "qty": 1,
            "price_list_rate": 0, "discount_percentage": 0, "rate": 0, "item_tax_rate": "{}",
        }))
        order_api.send_order(order)
        q = kitchen_api.get_station_queue(grouped)
        ticket = [t for t in q["tickets"] if t["order"] == order]
        self.assertTrue(ticket)
        self.assertEqual(ticket[0]["next_status"], "Processing")
        self.assertEqual(kitchen_api.advance(grouped, order)["status"], "Processing")
