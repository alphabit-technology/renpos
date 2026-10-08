# -*- coding: utf-8 -*-
"""Void reasons and the void audit log."""

import frappe
from frappe.tests.utils import FrappeTestCase

from renpos.api import order as order_api
from renpos.api import voids as voids_api
from renpos.tests.test_order_flow import (
	ITEM_A, ITEM_B, MANAGER, WAITER, setup_fixtures,
)
import json


class TestVoids(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.fx = setup_fixtures()
		voids_api.install_default_reasons()

	def tearDown(self):
		frappe.set_user("Administrator")

	def order_with_sent_item(self, ident):
		frappe.set_user(WAITER)
		order = order_api.add_order(self.fx["table"])["order"]["data"]["name"]
		order_api.push_item(order, json.dumps({
			"identifier": ident, "item_code": ITEM_A, "qty": 2, "price_list_rate": 10, "rate": 10,
			"discount_percentage": 0, "item_tax_rate": "{}",
		}))
		order_api.send_order(order)
		order_api.push_item(order, json.dumps({
			"identifier": ident + "-p", "item_code": ITEM_B, "qty": 1, "price_list_rate": 2.5, "rate": 2.5,
			"discount_percentage": 0, "item_tax_rate": "{}",
		}))
		return order

	def logs(self, order):
		return frappe.get_all("Ren Void Log", filters={"order_name": order},
		                      fields=["void_type", "reason", "note", "voided_by", "item_code", "qty", "amount",
		                              "status_at_void", "ordered_by"])

	def test_reasons_list(self):
		frappe.set_user(WAITER)
		names = [r.name for r in voids_api.get_void_reasons()]
		self.assertIn("Kitchen error", names)
		self.assertIn("Other", names)

	def test_pending_item_needs_no_reason(self):
		order = self.order_with_sent_item("v-pend")
		order_api.delete_item(order, "v-pend-p")
		self.assertEqual(self.logs(order), [])

	def test_sent_item_requires_reason_and_logs(self):
		order = self.order_with_sent_item("v-sent")
		frappe.set_user(MANAGER)
		self.assertRaises(frappe.ValidationError, order_api.delete_item, order, "v-sent")
		self.assertRaises(frappe.ValidationError, order_api.delete_item, order, "v-sent", reason="Nope")
		# "Other" needs a note
		self.assertRaises(frappe.ValidationError, order_api.delete_item, order, "v-sent", reason="Other")
		order_api.delete_item(order, "v-sent", reason="Other", note="spilled")
		(log,) = self.logs(order)
		self.assertEqual((log.void_type, log.reason, log.note, log.voided_by), ("Item", "Other", "spilled", MANAGER))
		self.assertEqual((log.item_code, log.qty, log.amount, log.status_at_void), (ITEM_A, 2, 20, "Sent"))
		self.assertEqual(log.ordered_by, WAITER)

	def test_void_order_with_sent_items(self):
		order = self.order_with_sent_item("v-ord")
		# waiter can't void an order with sent items
		self.assertRaises((frappe.PermissionError, frappe.ValidationError), order_api.delete_order, order, "Long wait")
		frappe.set_user(MANAGER)
		self.assertRaises(frappe.ValidationError, order_api.delete_order, order)
		order_api.delete_order(order, reason="Long wait")
		self.assertFalse(frappe.db.exists("Ren Order", order))
		logs = self.logs(order)
		self.assertEqual(len(logs), 1)  # only the sent item; the pending one isn't a void
		self.assertEqual((logs[0].void_type, logs[0].reason), ("Order", "Long wait"))

	def test_order_without_sent_items_voids_freely(self):
		frappe.set_user(WAITER)
		order = order_api.add_order(self.fx["table"])["order"]["data"]["name"]
		order_api.delete_order(order)
		self.assertFalse(frappe.db.exists("Ren Order", order))
