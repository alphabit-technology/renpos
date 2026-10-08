# -*- coding: utf-8 -*-
"""Tips on the invoice and the server (waiter) of each sale."""

import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from renpos.api import order as order_api
from renpos.tests.test_order_flow import (
	ITEM_A, ITEM_B, PROFILE, WAITER, open_register, setup_fixtures, _abbr,
)


def tips_account(company):
	name = f"_REN Tips Payable - {_abbr(company)}"
	if not frappe.db.exists("Account", name):
		parent = frappe.db.get_value("Account", {"company": company, "root_type": "Liability", "is_group": 1,
		                                         "account_name": ["like", "%Current Liabilities%"]}) \
			or frappe.db.get_value("Account", {"company": company, "root_type": "Liability", "is_group": 1})
		frappe.get_doc({"doctype": "Account", "account_name": "_REN Tips Payable", "company": company,
		                "parent_account": parent, "account_type": "Payable" if False else "",
		                "is_group": 0}).insert(ignore_permissions=True)
	return name


class TestTips(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.fx = setup_fixtures()
		cls.account = tips_account(cls.fx["company"])

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.set_value("POS Profile", PROFILE, {"ren_tip_account": self.account,
		                                             "ren_tip_percentages": "18, 20, 22%", "ren_tip_on": "Subtotal"})
		frappe.clear_document_cache("POS Profile", PROFILE)
		open_register(WAITER, self.fx["company"])

	def tearDown(self):
		frappe.set_user("Administrator")

	def order(self):
		frappe.set_user(WAITER)
		order = order_api.add_order(self.fx["table"])["order"]["data"]["name"]
		for code, qty, plr in ((ITEM_A, 2, 10), (ITEM_B, 1, 2.5)):
			order_api.push_item(order, json.dumps({
				"identifier": frappe.generate_hash(length=8), "item_code": code, "qty": qty,
				"price_list_rate": plr, "rate": plr, "discount_percentage": 0, "item_tax_rate": "{}",
			}))
		return order

	def test_summary_offers_tips(self):
		order = self.order()
		tips = order_api.get_payment_summary(order)["tips"]
		self.assertTrue(tips["enabled"])
		self.assertEqual(tips["percentages"], [18, 20, 22])
		self.assertAlmostEqual(tips["base"], 22.5)

	def test_payment_with_tip(self):
		order = self.order()
		# paying only the bill is not enough once a tip is added
		self.assertRaises(frappe.ValidationError, order_api.process_payment, order,
		                  json.dumps([{"mode_of_payment": "Credit Card", "amount": 22.5}]), 4.5)
		res = order_api.process_payment(order, json.dumps([
			{"mode_of_payment": "Credit Card", "amount": 13.5},
			{"mode_of_payment": "Credit Card", "amount": 13.5},
		]), 4.5)
		self.assertAlmostEqual(res["tip"], 4.5)
		inv = frappe.get_doc(res["invoice_doctype"], res["invoice"])
		self.assertAlmostEqual(flt(inv.grand_total), 27)
		tip_rows = [t for t in inv.taxes if t.account_head == self.account]
		self.assertEqual(len(tip_rows), 1)
		self.assertAlmostEqual(flt(tip_rows[0].tax_amount), 4.5)
		self.assertEqual(inv.ren_server, WAITER)
		self.assertAlmostEqual(flt(inv.ren_tip_amount), 4.5)

	def test_invalid_tips(self):
		order = self.order()
		pay = json.dumps([{"mode_of_payment": "Cash", "amount": 100}])
		self.assertRaises(frappe.ValidationError, order_api.process_payment, order, pay, -1)
		self.assertRaises(frappe.ValidationError, order_api.process_payment, order, pay, 50)  # > bill
		frappe.set_user("Administrator")
		frappe.db.set_value("POS Profile", PROFILE, "ren_tip_account", None)
		frappe.clear_document_cache("POS Profile", PROFILE)
		frappe.set_user(WAITER)
		self.assertRaises(frappe.ValidationError, order_api.process_payment, order, pay, 2)
		self.assertFalse(order_api.get_payment_summary(order)["tips"]["enabled"])
