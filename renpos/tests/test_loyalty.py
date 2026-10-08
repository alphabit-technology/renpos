# -*- coding: utf-8 -*-
"""Loyalty points: earned on the invoice, redeemed as part of the payment (api/loyalty.py)."""

import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from renpos.api import order as order_api
from renpos.tests.test_order_flow import (
    CUSTOMER, ITEM_A, WAITER, _abbr, open_register, setup_fixtures,
)

PROGRAM = "_REN Points"
GUEST = "_REN Loyal Guest"


class TestLoyalty(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.fx = setup_fixtures()
        company = cls.fx["company"]
        abbr = _abbr(company)
        expense = frappe.db.get_value("Account", {"company": company, "root_type": "Expense", "is_group": 0}, "name")
        if not frappe.db.exists("Loyalty Program", PROGRAM):
            frappe.get_doc({
                "doctype": "Loyalty Program", "loyalty_program_name": PROGRAM, "loyalty_program_type": "Single Tier Program",
                "company": company, "from_date": "2020-01-01", "conversion_factor": 0.5, "expiry_duration": 365,
                "expense_account": expense, "cost_center": f"Main - {abbr}",
                "collection_rules": [{"tier_name": "Base", "collection_factor": 1, "min_spent": 0}],
            }).insert(ignore_permissions=True)
        if not frappe.db.exists("Customer", GUEST):
            frappe.get_doc({"doctype": "Customer", "customer_name": GUEST, "loyalty_program": PROGRAM,
                            "customer_group": frappe.db.get_value("Customer Group", {"is_group": 0})}
                           ).insert(ignore_permissions=True)
        open_register(WAITER, company)

    def tearDown(self):
        frappe.set_user("Administrator")

    def order(self, qty=2):
        frappe.set_user(WAITER)
        order = order_api.add_order(self.fx["table"])["order"]["data"]["name"]
        order_api.push_item(order, json.dumps({
            "identifier": frappe.generate_hash(length=10), "item_code": ITEM_A, "qty": qty, "price_list_rate": 10,
            "rate": 10, "discount_percentage": 0, "item_tax_rate": "{}"}))
        order_api.set_customer(order, GUEST)
        return order

    def points(self):
        from renpos.api.loyalty import _points
        return _points(GUEST, PROGRAM, self.fx["company"])

    def test_earn_then_redeem(self):
        start = self.points()
        order = self.order()
        summary = order_api.get_payment_summary(order)
        self.assertEqual(summary["loyalty"]["program"], PROGRAM)
        due = flt(summary["amount_due"])
        self.assertEqual(summary["loyalty"]["earns"], int(due))
        res = order_api.process_payment(order, json.dumps([{"mode_of_payment": "Cash", "amount": due}]))
        self.assertEqual(res["points_earned"], int(due))
        self.assertEqual(self.points(), start + int(due))

        # the next bill: use 10 points (0.5 each = 5.00), pay the rest in cash
        order = self.order()
        summary = order_api.get_payment_summary(order, 0, 10)
        self.assertAlmostEqual(flt(summary["amount_due"]), due - 5)
        self.assertEqual(summary["loyalty"]["used_points"], 10)
        res = order_api.process_payment(order, json.dumps([{"mode_of_payment": "Cash", "amount": due - 5}]), 0, 10)
        inv = frappe.get_doc(res["invoice_doctype"], res["invoice"])
        self.assertEqual((inv.redeem_loyalty_points, inv.loyalty_points, flt(inv.loyalty_amount)), (1, 10, 5))
        self.assertEqual(res["loyalty_amount"], 5)

    def test_points_can_pay_it_all_and_never_more(self):
        order = self.order(qty=1)
        due = flt(order_api.get_payment_summary(order)["amount_due"])
        while self.points() < due * 2:  # enough points to cover the bill
            o = self.order(qty=5)
            d = flt(order_api.get_payment_summary(o)["amount_due"])
            order_api.process_payment(o, json.dumps([{"mode_of_payment": "Cash", "amount": d}]))
        summary = order_api.get_payment_summary(order)
        self.assertEqual(summary["loyalty"]["max_points"], int(due / 0.5))
        self.assertRaises(frappe.ValidationError, order_api.get_payment_summary, order, 0, int(due / 0.5) + 2)
        res = order_api.process_payment(order, json.dumps([]), 0, int(due / 0.5))
        self.assertEqual(flt(res["loyalty_amount"]), due)

    def test_without_a_program_nothing_shows(self):
        frappe.set_user(WAITER)
        order = order_api.add_order(self.fx["table"])["order"]["data"]["name"]
        order_api.push_item(order, json.dumps({
            "identifier": frappe.generate_hash(length=10), "item_code": ITEM_A, "qty": 1, "price_list_rate": 10,
            "rate": 10, "discount_percentage": 0, "item_tax_rate": "{}"}))
        order_api.set_customer(order, CUSTOMER)  # a walk-in guest, no program
        self.assertIsNone(order_api.get_payment_summary(order)["loyalty"])
        self.assertRaises(frappe.ValidationError, order_api.get_payment_summary, order, 0, 5)

    def test_join_at_the_register(self):
        guest = "_REN New Guest"
        if not frappe.db.exists("Customer", guest):
            frappe.get_doc({"doctype": "Customer", "customer_name": guest,
                            "customer_group": frappe.db.get_value("Customer Group", {"is_group": 0})}
                           ).insert(ignore_permissions=True)
        frappe.db.set_value("Customer", guest, "loyalty_program", None)
        frappe.set_user(WAITER)
        order = order_api.add_order(self.fx["table"])["order"]["data"]["name"]
        order_api.push_item(order, json.dumps({
            "identifier": frappe.generate_hash(length=10), "item_code": ITEM_A, "qty": 1, "price_list_rate": 10,
            "rate": 10, "discount_percentage": 0, "item_tax_rate": "{}"}))
        order_api.set_customer(order, CUSTOMER)
        self.assertIsNone(order_api.get_payment_summary(order)["loyalty_join"])  # the walk-in customer never joins
        order_api.set_customer(order, guest)
        summary = order_api.get_payment_summary(order)
        self.assertTrue(summary["loyalty_join"])
        from renpos.api.loyalty import join
        join(order)
        self.assertEqual(order_api.get_payment_summary(order)["loyalty"]["points"], 0)
