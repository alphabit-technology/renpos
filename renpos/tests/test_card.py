# -*- coding: utf-8 -*-
"""Stripe Terminal card payments with a fake Stripe API."""

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from renpos.api import card as card_api
from renpos.api import order as order_api
from renpos.tests.test_order_flow import (
	ITEM_A, ITEM_B, MANAGER, PROFILE, WAITER, open_register, setup_fixtures,
)

READER = "tmr_TEST123"


class FakeStripe:
	def __init__(self):
		self.intents = {}
		self.order = []  # intent ids in creation order
		self.reader_action = None
		self.calls = []
		self.reader_offline = False

	def __call__(self, method, path, data=None):
		self.calls.append((method, path, data))
		if path == "/payment_intents" and method == "POST":
			pi = f"pi_{frappe.generate_hash(length=8)}"
			self.order.append(pi)
			self.intents[pi] = {"id": pi, "status": "requires_payment_method", "amount": data["amount"]}
			return self.intents[pi]
		if path.startswith("/terminal/readers/") and path.endswith("/process_payment_intent"):
			if self.reader_offline:
				frappe.throw("Reader is currently offline")
			self.reader_action = {"type": "process_payment_intent", "status": "in_progress",
			                      "process_payment_intent": {"payment_intent": data["payment_intent"]}}
			return {"id": READER, "action": self.reader_action}
		if path.startswith("/terminal/readers/") and path.endswith("/cancel_action"):
			self.reader_action = None
			return {"id": READER}
		if path.startswith("/terminal/readers/"):
			return {"id": READER, "action": self.reader_action}
		if path.startswith("/payment_intents/") and path.endswith("/cancel"):
			pi = path.split("/")[2]
			if self.intents[pi]["status"] == "succeeded":
				frappe.throw("You cannot cancel this PaymentIntent because it has a status of succeeded.")
			self.intents[pi]["status"] = "canceled"
			return self.intents[pi]
		if path.startswith("/payment_intents/"):
			pi = path.split("/")[2].split("?")[0]
			return self.intents[pi]
		raise AssertionError(f"unexpected call {method} {path}")

	# what the customer does on the reader
	def approve(self, last4="4242"):
		pi = self.reader_action["process_payment_intent"]["payment_intent"]
		self.intents[pi].update({"status": "succeeded", "latest_charge": {
			"payment_method_details": {"card_present": {"brand": "visa", "last4": last4}}}})
		self.reader_action["status"] = "succeeded"

	def decline(self):
		self.reader_action.update({"status": "failed", "failure_code": "card_declined",
		                           "failure_message": "Your card has insufficient funds."})


class TestCard(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.fx = setup_fixtures()
		settings = frappe.get_doc("Ren Settings")
		settings.stripe_enabled = 1
		settings.stripe_secret_key = "sk_test_fake"
		settings.set("stripe_readers", [{"label": "Front", "reader_id": READER, "pos_profile": PROFILE,
		                                 "mode_of_payment": "Credit Card"}])
		settings.flags.ignore_mandatory = True
		settings.save(ignore_permissions=True)

	def setUp(self):
		frappe.set_user("Administrator")
		open_register(WAITER, self.fx["company"])
		self.fake = FakeStripe()
		self.patch = patch.object(card_api, "stripe", self.fake)
		self.patch.start()

	def tearDown(self):
		self.patch.stop()
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

	def test_readers_in_summary(self):
		order = self.order()
		readers = order_api.get_payment_summary(order)["card_readers"]
		self.assertEqual(readers, [{"reader": READER, "label": "Front", "mode_of_payment": "Credit Card"}])

	def test_approved_card_pays_order(self):
		order = self.order()
		cp = card_api.start_card_payment(order, READER, 22.5)
		self.assertEqual(cp["status"], "Pending")
		self.assertEqual(self.fake.intents[self.fake.order[0]]["amount"], 2250)  # cents
		self.assertEqual(card_api.card_payment_status(cp["name"])["status"], "Pending")

		self.fake.approve()
		st = card_api.card_payment_status(cp["name"])
		self.assertEqual((st["status"], st["card"]), ("Succeeded", "Visa ···· 4242"))

		res = order_api.process_payment(order, json.dumps([
			{"mode_of_payment": "Credit Card", "amount": 22.5, "card_payment": cp["name"]}]))
		inv = frappe.db.get_value("Ren Card Payment", cp["name"], ["invoice", "invoice_doctype"], as_dict=True)
		self.assertEqual((inv.invoice, inv.invoice_doctype), (res["invoice"], res["invoice_doctype"]))

	def test_card_payment_cant_be_faked_or_reused(self):
		order = self.order()
		cp = card_api.start_card_payment(order, READER, 22.5)
		pay = lambda amount=22.5, name=cp["name"]: order_api.process_payment(order, json.dumps([
			{"mode_of_payment": "Credit Card", "amount": amount, "card_payment": name}]))
		self.assertRaises(frappe.ValidationError, pay)          # not approved yet
		self.fake.approve()
		card_api.card_payment_status(cp["name"])
		self.assertRaises(frappe.ValidationError, pay, 30)      # different amount
		pay()
		other = self.order()
		self.assertRaises(frappe.ValidationError, order_api.process_payment, other, json.dumps([
			{"mode_of_payment": "Credit Card", "amount": 22.5, "card_payment": cp["name"]}]))  # other order / reused

	def test_declined_and_canceled(self):
		order = self.order()
		cp = card_api.start_card_payment(order, READER, 10)
		self.fake.decline()
		st = card_api.card_payment_status(cp["name"])
		self.assertEqual(st["status"], "Failed")
		self.assertIn("insufficient", st["failure_message"])
		self.assertEqual(self.fake.intents[self.fake.order[0]]["status"], "canceled")

		cp2 = card_api.start_card_payment(order, READER, 10)
		self.assertEqual(card_api.cancel_card_payment(cp2["name"])["status"], "Canceled")
		self.assertEqual(self.fake.intents[self.fake.order[1]]["status"], "canceled")

	def test_offline_reader(self):
		order = self.order()
		self.fake.reader_offline = True
		self.assertRaises(frappe.ValidationError, card_api.start_card_payment, order, READER, 10)
		row = frappe.get_all("Ren Card Payment", filters={"order_name": order}, fields=["status"])
		self.assertEqual(row[0].status, "Failed")
		self.assertEqual(self.fake.intents[self.fake.order[0]]["status"], "canceled")

	def test_permissions(self):
		order = self.order()
		frappe.set_user(MANAGER)  # not a cashier
		self.assertRaises(frappe.PermissionError, card_api.start_card_payment, order, READER, 10)
		frappe.set_user(WAITER)
		self.assertRaises(frappe.ValidationError, card_api.start_card_payment, order, "tmr_OTHER", 10)

	def test_review_guards(self):
		order = self.order()
		cp = card_api.start_card_payment(order, READER, 11.25)
		# one card flow at a time
		self.assertRaises(frappe.ValidationError, card_api.start_card_payment, order, READER, 5)
		# customer taps right as the cashier cancels: the charge is kept
		self.fake.approve()
		self.assertEqual(card_api.cancel_card_payment(cp["name"])["status"], "Succeeded")
		# summary brings the approved charge back (panel reopened)
		summary = order_api.get_payment_summary(order)
		self.assertEqual([c["name"] for c in summary["card_payments"]], [cp["name"]])
		# the order can't be voided with a card charge on it
		frappe.set_user("Administrator")
		self.assertRaises(frappe.ValidationError, order_api.delete_order, order)
		frappe.set_user(WAITER)
		# a charge listed twice / a reader mode without the reader is refused
		row = {"mode_of_payment": "Credit Card", "amount": 11.25, "card_payment": cp["name"]}
		self.assertRaises(frappe.ValidationError, order_api.process_payment, order, json.dumps([row, row]))
		self.assertRaises(frappe.ValidationError, order_api.process_payment, order, json.dumps([
			row, {"mode_of_payment": "Credit Card", "amount": 11.25}]))
		# more than the bill + a full tip is refused
		self.assertRaises(frappe.ValidationError, card_api.start_card_payment, order, READER, 40)
		cp2 = card_api.start_card_payment(order, READER, 11.25)
		self.fake.approve()
		card_api.card_payment_status(cp2["name"])
		res = order_api.process_payment(order, json.dumps([row, {**row, "card_payment": cp2["name"]}]))
		self.assertEqual(res["status"], "Invoiced")

	def test_summary_with_tip_uses_server_rounding(self):
		from renpos.tests.test_tips import tips_account
		frappe.set_user("Administrator")
		frappe.db.set_value("POS Profile", PROFILE, "ren_tip_account", tips_account(self.fx["company"]))
		frappe.clear_document_cache("POS Profile", PROFILE)
		order = self.order()
		s = order_api.get_payment_summary(order, 3.06)
		self.assertAlmostEqual(s["tip"], 3.06)
		self.assertAlmostEqual(flt(s["amount_due"]), flt(s["grand_total"]) if not s["rounding_adjustment"] else flt(s["amount_due"]))
		self.assertAlmostEqual(flt(s["grand_total"]), 22.5 + 3.06)
