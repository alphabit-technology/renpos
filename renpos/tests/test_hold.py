# -*- coding: utf-8 -*-
"""Hold and fire: a held line waits for its course; Send leaves it, Fire sends it."""

import json

import frappe

from renpos.api import kitchen as kitchen_api
from renpos.api import order as order_api
from renpos.tests.test_kitchen import DRINK, FOOD, KitchenCase, make_station, ticket_of
from renpos.tests.test_order_flow import WAITER

R = "-" + frappe.generate_hash(length=6)


class TestHoldAndFire(KitchenCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.line = make_station(cls.fx["floor"], "_REN Hold Line", groups=("_REN Food", "_REN Drinks"))

    def push_held(self, order, ident, code, hold):
        frappe.set_user(WAITER)
        order_api.push_item(order, json.dumps({
            "identifier": ident, "item_code": code, "qty": 1, "ren_hold": hold,
            "price_list_rate": 0, "discount_percentage": 0, "rate": 0, "item_tax_rate": "{}",
        }))

    def test_send_leaves_held_lines_and_fire_sends_them(self):
        frappe.set_user(WAITER)
        order = order_api.add_order(self.fx["table"])["order"]["data"]["name"]
        self.push_held(order, "starter" + R, DRINK, 0)
        self.push_held(order, "main" + R, FOOD, 1)

        order_api.send_order(order)
        self.assertEqual(self.status("starter" + R), "Sent")
        self.assertEqual(self.status("main" + R), "Pending")
        frappe.set_user("Administrator")
        items = [i["identifier"] for t in ticket_of(kitchen_api.get_station_queue(self.line), order) for i in t["items"]]
        self.assertEqual(items, ["starter" + R])  # the kitchen doesn't see the held main yet

        frappe.set_user(WAITER)
        self.assertRaises(frappe.ValidationError, order_api.send_order, order)  # nothing else to send
        order_api.send_order(order, fire=1)
        self.assertEqual(self.status("main" + R), "Sent")
        self.assertEqual(frappe.db.get_value("Ren Order Item", {"identifier": "main" + R}, "ren_hold"), 0)
        frappe.set_user("Administrator")
        tickets = ticket_of(kitchen_api.get_station_queue(self.line), order)
        self.assertEqual(len(tickets), 2)  # the fire is its own round
        frappe.set_user(WAITER)
        self.assertRaises(frappe.ValidationError, order_api.send_order, order, 1)  # nothing held any more

    def test_a_held_line_can_be_released(self):
        frappe.set_user(WAITER)
        order = order_api.add_order(self.fx["table"])["order"]["data"]["name"]
        self.push_held(order, "late" + R, FOOD, 1)
        self.push_held(order, "late" + R, FOOD, 0)  # released before sending
        order_api.send_order(order)
        self.assertEqual(self.status("late" + R), "Sent")
