# -*- coding: utf-8 -*-
"""Delivery by zones: picking the branch, phone orders, the fee on the bill, online delivery (api/delivery.py)."""

import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from renpos.api import delivery, online
from renpos.api import order as order_api
from renpos.api.guards import current_pos_profile
from renpos.api.restaurant import my_restaurants, switch_restaurant
from renpos.tests.test_order_flow import (
    CASHIER2, ITEM_A, PROFILE, RESTAURANT, WAITER, _abbr, grant_floor, setup_fixtures,
)

BRANCH_B = "_REN Branch B"
PROFILE_B = "_REN Branch B POS"


def _table(room, description):
	name = frappe.db.get_value("Ren Table", {"room": room, "description": description})
	return name or frappe.get_doc({"doctype": "Ren Table", "room": room, "description": description,
	                               "no_of_seats": 1}).insert(ignore_permissions=True).name


class TestDelivery(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.fx = setup_fixtures()
		company = cls.fx["company"]
		abbr = _abbr(company)
		cls.fee_account = f"Sales - {abbr}"

		# branch A: the test restaurant, 02128 exactly
		cls.table_a = _table(cls.fx["room"], "Delivery")
		a = frappe.get_doc("Ren Restaurant", RESTAURANT)
		a.delivery, a.delivery_table, a.delivery_online, a.delivery_fee_account = 1, cls.table_a, 1, cls.fee_account
		a.set("delivery_zones", [{"zone_name": "Eastie", "zip_codes": "02128", "fee": 3, "minimum_order": 15,
		                          "eta_minutes": 40}])
		a.save(ignore_permissions=True)

		# branch B: every 021* ZIP code, faster but dearer
		if not frappe.db.exists("Ren Restaurant", BRANCH_B):
			frappe.get_doc({"doctype": "Ren Restaurant", "restaurant_name": BRANCH_B, "company": company,
			                "active": 1}).insert(ignore_permissions=True)
		if not frappe.db.exists("POS Profile", PROFILE_B):
			src = frappe.get_doc("POS Profile", PROFILE)
			b_profile = frappe.copy_doc(src)
			b_profile.__newname = PROFILE_B
			b_profile.name = PROFILE_B
			b_profile.ren_restaurant = BRANCH_B
			b_profile.set("applicable_for_users", [{"user": WAITER, "default": 0}])
			b_profile.insert(ignore_permissions=True)
		floor = frappe.db.get_value("Ren Floor", {"restaurant": BRANCH_B}) or frappe.get_doc(
			{"doctype": "Ren Floor", "restaurant": BRANCH_B, "description": "B floor"}).insert(ignore_permissions=True).name
		room = frappe.db.get_value("Ren Room", {"floor": floor}) or frappe.get_doc(
			{"doctype": "Ren Room", "floor": floor, "description": "B counter"}).insert(ignore_permissions=True).name
		cls.table_b = _table(room, "Delivery B")
		grant_floor(WAITER, floor, PROFILE_B)
		b = frappe.get_doc("Ren Restaurant", BRANCH_B)
		b.delivery, b.delivery_table, b.delivery_online, b.delivery_fee_account = 1, cls.table_b, 1, cls.fee_account
		b.set("delivery_zones", [{"zone_name": "Boston", "zip_codes": "021*", "fee": 5, "minimum_order": 0,
		                          "eta_minutes": 30}])
		b.save(ignore_permissions=True)

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.defaults.clear_user_default("ren_current_restaurant", WAITER)
		for name in frappe.get_all("Ren Order", filters={"table": ["in", [self.table_a, self.table_b]]}, pluck="name"):
			frappe.flags.ren_order_api = True
			frappe.delete_doc("Ren Order", name, force=True, ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.defaults.clear_user_default("ren_current_restaurant", WAITER)

	# ── which branch ──

	def test_zip_codes_pick_the_branch(self):
		self.assertEqual(delivery.normalize_zip("02128-4410"), "02128")
		self.assertEqual(delivery.zip_patterns("02128, 02129 021*"), ["02128", "02129", "021*"])
		self.assertEqual(delivery.invalid_zip_patterns("02128 2128 021* abc"), ["2128", "abc"])
		# exact beats the prefix (even if the prefix branch is faster)
		self.assertEqual([q["restaurant"] for q in delivery.branches_for("02128")], [RESTAURANT, BRANCH_B])
		self.assertEqual([q["restaurant"] for q in delivery.branches_for("02130")], [BRANCH_B])
		self.assertEqual(delivery.branches_for("99999"), [])
		self.assertEqual(delivery.branches_for("02128")[0]["fee"], 3)
		# outside its zones a branch can still be chosen by hand: no zone, no fee
		q = delivery.quote_for(RESTAURANT, "02130")
		self.assertFalse(q["in_zone"])
		self.assertEqual(q["fee"], 0)

	def test_bad_zone_is_refused(self):
		a = frappe.get_doc("Ren Restaurant", RESTAURANT)
		a.append("delivery_zones", {"zone_name": "Bad", "zip_codes": "2128"})
		self.assertRaises(frappe.ValidationError, a.save)

	# ── phone orders ──

	def test_phone_order_lands_on_the_branch(self):
		frappe.set_user(WAITER)
		r = delivery.new_order("02128", customer_name="Ana Phone", phone="(617) 555-0142",
		                       address_line="12 Main St", city="Boston", save_address=1, notes="Ring twice")
		self.assertFalse(r["switch"])
		self.assertEqual(r["table"], self.table_a)
		o = frappe.get_doc("Ren Order", r["order"])
		self.assertEqual((o.ren_origin, o.ren_delivery, flt(o.ren_delivery_fee), o.ren_delivery_zone),
		                 ("Phone", 1, 3, "Eastie"))
		self.assertIn("12 Main St", o.notes)
		self.assertIn("Ring twice", o.notes)
		self.assertTrue(o.customer and o.address)
		# the customer is found by phone next time, with the address
		found = delivery.lookup("617-555-0142")
		self.assertEqual(found[0]["customer"], o.customer)
		self.assertEqual(found[0]["addresses"][0]["zip"], "02128")

	def test_phone_order_for_another_branch(self):
		frappe.set_user(WAITER)
		r = delivery.new_order("02130", address_line="5 Elm St")
		self.assertEqual((r["restaurant"], r["pos_profile"], r["switch"]), (BRANCH_B, PROFILE_B, True))
		self.assertEqual(frappe.db.get_value("Ren Order", r["order"], "restaurant"), BRANCH_B)
		# someone who doesn't work branch B can't send it there
		frappe.set_user(CASHIER2)
		self.assertRaises(frappe.PermissionError, delivery.new_order, "02130", address_line="5 Elm St")

	def test_switch_restaurant(self):
		frappe.set_user(WAITER)
		self.assertEqual({b["restaurant"] for b in my_restaurants()}, {RESTAURANT, BRANCH_B})
		switch_restaurant(BRANCH_B)
		self.assertEqual(current_pos_profile(), PROFILE_B)  # the profile he charges with there
		self.assertEqual(my_restaurants()[0]["restaurant"], BRANCH_B)
		frappe.set_user(CASHIER2)
		self.assertRaises(frappe.PermissionError, switch_restaurant, BRANCH_B)

	def test_fee_on_the_bill(self):
		from renpos.api.invoicing import build_invoice_preview
		frappe.set_user(WAITER)
		r = delivery.new_order("02128", address_line="12 Main St")
		order_api.push_item(r["order"], json.dumps({"identifier": "d-1", "item_code": ITEM_A, "qty": 2,
		                                            "price_list_rate": 10, "rate": 10, "item_tax_rate": "{}"}))
		frappe.set_user("Administrator")
		order = frappe.get_doc("Ren Order", r["order"])
		self.assertEqual(delivery.below_minimum(order), 0)  # 20 >= 15
		inv = build_invoice_preview(order)
		fee = [t for t in inv.taxes if t.description == "Delivery fee"]
		self.assertEqual(flt(fee[0].tax_amount), 3)
		self.assertEqual(flt(inv.grand_total), 23)
		self.assertEqual(order_api._order_dict(order)["ren_delivery_fee"], 3)
		# no account: a clear message
		frappe.db.set_value("Ren Restaurant", RESTAURANT, "delivery_fee_account", None)
		try:
			self.assertRaises(frappe.ValidationError, build_invoice_preview, order)
		finally:
			frappe.db.set_value("Ren Restaurant", RESTAURANT, "delivery_fee_account", self.fee_account)

	# ── online ──

	def test_online_delivery(self):
		frappe.set_user("Guest")
		frappe.local.request_ip = "127.0.0.1"
		self.assertEqual(online.delivery_check("02130")["restaurant"], BRANCH_B)
		self.assertRaises(frappe.ValidationError, online.delivery_check, "99999")
		m = online.menu(r=RESTAURANT, d="02128")
		self.assertEqual(m["mode"], "delivery")
		self.assertEqual(m["delivery"]["fee"], 3)
		# branch A doesn't cover 02130
		self.assertRaises(frappe.ValidationError, online.menu, r=RESTAURANT, d="02130")
		items = json.dumps([{"item_code": ITEM_A, "qty": 1}])
		args = dict(r=RESTAURANT, d="02128", guest_name="Bo", phone="6175550100", address_line="1 Pier Rd")
		self.assertRaises(frappe.ValidationError, online.place, items, **args)  # 10 < 15 minimum
		res = online.place(json.dumps([{"item_code": ITEM_A, "qty": 2}]), **args)
		self.assertEqual(res["mode"], "delivery")
		self.assertEqual(flt(res["delivery_fee"]), 3)
		frappe.set_user("Administrator")
		o = frappe.get_doc("Ren Order", {"ren_guest_token": res["token"]})
		self.assertEqual((o.table, o.ren_origin, o.ren_delivery_zip), (self.table_a, "Online", "02128"))
		self.assertEqual({r.status for r in o.entry_items}, {"Sent"})  # ASAP: straight to the kitchen

	def test_guest_sees_the_driver(self):
		frappe.set_user("Guest")
		frappe.local.request_ip = "127.0.0.1"
		res = online.place(json.dumps([{"item_code": ITEM_A, "qty": 2}]), r=RESTAURANT, d="02128",
		                   guest_name="Bo", phone="6175550100", address_line="1 Pier Rd")
		frappe.set_user("Administrator")
		name = frappe.db.get_value("Ren Order", {"ren_guest_token": res["token"]})
		frappe.db.set_value("Ren Order", name, {"ren_driver_name": "Luis Perez", "ren_dispatched_at": frappe.utils.now_datetime()})
		s = online.status(res["token"])
		self.assertEqual((s["state"], s["driver"]), ("on_the_way", "Luis"))
		frappe.db.set_value("Ren Order", name, "ren_delivered_at", frappe.utils.now_datetime())
		self.assertEqual(online.status(res["token"])["state"], "delivered")
