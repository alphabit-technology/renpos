# -*- coding: utf-8 -*-
"""Cash register open / shift report / close."""

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from renpos.api import order as order_api
from renpos.api import register as reg
from renpos.tests.test_order_flow import (
	CASHIER2, ITEM_A, ITEM_B, MANAGER, PROFILE, WAITER, setup_fixtures,
)


def close_all(user):
	for name in frappe.get_all("POS Opening Entry", filters={"user": user, "pos_profile": PROFILE, "docstatus": 1,
	                                                         "pos_closing_entry": ["in", ["", None]]}, pluck="name"):
		doc = frappe.get_doc("POS Opening Entry", name)
		try:
			doc.cancel()
		except frappe.ValidationError:
			# it has invoices (e.g. left by a manual test): close it properly
			frappe.clear_messages()
			from erpnext.accounts.doctype.pos_closing_entry.pos_closing_entry import make_closing_entry_from_opening
			closing = make_closing_entry_from_opening(doc)
			for row in closing.payment_reconciliation:
				row.closing_amount = row.expected_amount
			closing.insert(ignore_permissions=True)
			closing.submit()


class TestRegister(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.fx = setup_fixtures()

	def setUp(self):
		frappe.set_user("Administrator")
		close_all(WAITER)
		close_all(CASHIER2)

	def tearDown(self):
		frappe.set_user("Administrator")

	def sell(self, amount_paid):
		order = order_api.add_order(self.fx["table"])["order"]["data"]["name"]
		for code, qty, plr in ((ITEM_A, 2, 10), (ITEM_B, 1, 2.5)):
			order_api.push_item(order, json.dumps({
				"identifier": frappe.generate_hash(length=8), "item_code": code, "qty": qty,
				"price_list_rate": plr, "rate": plr, "discount_percentage": 0, "item_tax_rate": "{}",
			}))
		return order_api.process_payment(order, json.dumps([{"mode_of_payment": "Cash", "amount": amount_paid}]))

	def test_full_shift(self):
		frappe.set_user(WAITER)
		self.assertEqual(reg.get_register(PROFILE)["status"], "closed")

		st = reg.open_register(PROFILE, json.dumps([{"mode_of_payment": "Cash", "opening_amount": 50}]))
		self.assertEqual(st["status"], "open")
		cash = next(p for p in st["report"]["payments"] if p["mode_of_payment"] == "Cash")
		self.assertEqual((cash["opening"], cash["expected"]), (50, 50))
		self.assertRaises(frappe.ValidationError, reg.open_register, PROFILE, "[]")

		self.sell(30)  # 22.5 due, 7.5 change
		report = reg.get_register(PROFILE)["report"]
		self.assertEqual(report["invoices"], 1)
		self.assertAlmostEqual(report["grand_total"], 22.5)
		cash = next(p for p in report["payments"] if p["mode_of_payment"] == "Cash")
		self.assertAlmostEqual(cash["expected"], 72.5)

		preview = reg.close_register(PROFILE, preview=1)
		row = next(r for r in preview["reconciliation"] if r["mode_of_payment"] == "Cash")
		self.assertAlmostEqual(row["expected"], 72.5)

		# every mode must be counted
		self.assertRaises(frappe.ValidationError, reg.close_register, PROFILE,
		                  json.dumps([{"mode_of_payment": "Cash", "closing_amount": 70}]))
		res = reg.close_register(PROFILE, json.dumps([
			{"mode_of_payment": "Cash", "closing_amount": 70},
			{"mode_of_payment": "Credit Card", "closing_amount": 0},
		]))
		row = next(r for r in res["reconciliation"] if r["mode_of_payment"] == "Cash")
		self.assertAlmostEqual(row["difference"], -2.5)
		self.assertTrue(res["closing_entry"])
		self.assertEqual(frappe.db.get_value("POS Closing Entry", res["closing_entry"], "docstatus"), 1)
		self.assertEqual(reg.get_register(PROFILE)["status"], "closed")

	def test_non_cashier(self):
		frappe.set_user(MANAGER)
		self.assertEqual(reg.get_register(PROFILE)["status"], "no_permission")
		self.assertRaises(frappe.PermissionError, reg.open_register, PROFILE, "[]")

	def test_invalid_opening(self):
		frappe.set_user(WAITER)
		self.assertRaises(frappe.ValidationError, reg.open_register, PROFILE,
		                  json.dumps([{"mode_of_payment": "Bitcoin", "opening_amount": 1}]))
		self.assertRaises(frappe.ValidationError, reg.open_register, PROFILE,
		                  json.dumps([{"mode_of_payment": "Cash", "opening_amount": -1}]))

	def test_register_in_use_by_someone_else(self):
		# ERPNext v16: one open register per POS Profile, whoever opened it
		frappe.set_user(CASHIER2)
		reg.open_register(PROFILE, json.dumps([{"mode_of_payment": "Cash", "opening_amount": 20}]))
		frappe.set_user(WAITER)
		st = reg.get_register(PROFILE)
		self.assertEqual((st["status"], st["opening"]["user"], st["can_close"]), ("taken", CASHIER2, False))
		self.assertRaises(frappe.ValidationError, reg.open_register, PROFILE, "[]")
		self.assertRaises(frappe.PermissionError, reg.close_register, PROFILE, "[]", 0, st["opening"]["name"])

		# a manager counts and closes it; then the cashier opens their own
		frappe.set_user("Administrator")
		st = reg.get_register(PROFILE)
		self.assertTrue(st["can_close"])
		res = reg.close_register(PROFILE, json.dumps([{"mode_of_payment": m["mode_of_payment"], "closing_amount": m["expected"]}
		                                             for m in st["report"]["payments"]]), 0, st["opening"]["name"])
		self.assertTrue(res["closing_entry"])
		frappe.set_user(WAITER)
		self.assertEqual(reg.get_register(PROFILE)["status"], "closed")
		self.assertEqual(reg.open_register(PROFILE, "[]")["status"], "open")
