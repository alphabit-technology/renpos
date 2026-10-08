# -*- coding: utf-8 -*-
"""
End-to-end tests for the order / payment API used by the React client.

Run:
    bench --site <site> set-config allow_tests true
    bench --site <site> run-tests --module renpos.tests.test_order_flow

Needs a site with ERPNext set up (a company with a "Cash" account and a
"Stores" warehouse). Fixtures are created in setUpClass and everything is
rolled back afterwards.
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, getdate, now_datetime, nowdate

from renpos.api import order as order_api
from renpos.api import ren as ren_api

WAITER = "ren-waiter@test.local"      # Restaurant User + Accounts User (cashier, own register)
CASHIER2 = "ren-cashier2@test.local"  # cashier roles, in POS Profile, but no open register
MANAGER = "ren-manager@test.local"    # Restaurant Manager only: can't take payments
OUTSIDER = "ren-outsider@test.local"  # no restaurant role

PROFILE = "_REN Test POS"
RESTAURANT = "_REN Test Restaurant"
CUSTOMER = "_REN Test Customer"
ITEM_A = "_REN-BURGER"   # 10.00
ITEM_B = "_REN-SODA"     # 2.50


def _company():
    return frappe.defaults.get_global_default("company") or frappe.get_all("Company", pluck="name")[0]


def _abbr(company):
    return frappe.get_cached_value("Company", company, "abbr")


def _ensure_user(email, roles):
    if not frappe.db.exists("User", email):
        frappe.get_doc({
            "doctype": "User", "email": email, "first_name": email.split("@")[0],
            "send_welcome_email": 0, "user_type": "System User",
        }).insert(ignore_permissions=True)
    user = frappe.get_doc("User", email)
    user.add_roles(*roles)


def _ensure_item(code, price):
    if not frappe.db.exists("Item", code):
        frappe.get_doc({
            "doctype": "Item", "item_code": code, "item_name": code,
            "item_group": "Products", "stock_uom": "Nos",
            "is_stock_item": 0, "is_sales_item": 1,
        }).insert(ignore_permissions=True)
    if not frappe.db.exists("Item Price", {"item_code": code, "price_list": "Standard Selling"}):
        frappe.get_doc({
            "doctype": "Item Price", "item_code": code,
            "price_list": "Standard Selling", "price_list_rate": price,
        }).insert(ignore_permissions=True)


def _ensure_mode_account(mode, company, account):
    mop = frappe.get_doc("Mode of Payment", mode)
    if not any(a.company == company for a in mop.accounts):
        mop.append("accounts", {"company": company, "default_account": account})
        mop.save(ignore_permissions=True)


def setup_fixtures():
    company = _company()
    abbr = _abbr(company)

    cashier = ["Restaurant User", "Accounts User", "Sales Manager"]
    _ensure_user(WAITER, cashier)
    _ensure_user(CASHIER2, cashier)
    _ensure_user(MANAGER, ["Restaurant Manager"])
    _ensure_user(OUTSIDER, ["Sales User"])
    _ensure_item(ITEM_A, 10)
    _ensure_item(ITEM_B, 2.5)
    _ensure_mode_account("Cash", company, f"Cash - {abbr}")
    _ensure_mode_account("Credit Card", company, f"Cash - {abbr}")

    if not frappe.db.exists("Customer", CUSTOMER):
        frappe.get_doc({
            "doctype": "Customer", "customer_name": CUSTOMER,
            "customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}) or "All Customer Groups",
            "territory": frappe.db.get_value("Territory", {"is_group": 0}) or "All Territories",
        }).insert(ignore_permissions=True)

    if not frappe.db.exists("Ren Restaurant", RESTAURANT):
        frappe.get_doc({
            "doctype": "Ren Restaurant", "restaurant_name": RESTAURANT,
            "company": company, "active": 1, "default_customer": CUSTOMER,
        }).insert(ignore_permissions=True)

    if not frappe.db.exists("POS Profile", PROFILE):
        frappe.get_doc({
            "doctype": "POS Profile", "__newname": PROFILE, "name": PROFILE,
            "company": company, "currency": "USD", "customer": CUSTOMER,
            "warehouse": f"Stores - {abbr}", "selling_price_list": "Standard Selling",
            "write_off_account": f"Write Off - {abbr}",
            "write_off_cost_center": f"Main - {abbr}", "write_off_limit": 0,
            "update_stock": 0, "ren_tax_inclusive": 0,
            "ren_restaurant": RESTAURANT,
            "payments": [
                {"mode_of_payment": "Cash", "default": 1},
                {"mode_of_payment": "Credit Card"},
            ],
            "applicable_for_users": [{"user": WAITER, "default": 1}, {"user": CASHIER2}],
        }).insert(ignore_permissions=True)

    floor = frappe.db.get_value("Ren Floor", {"restaurant": RESTAURANT})
    if not floor:
        floor = frappe.get_doc({"doctype": "Ren Floor", "restaurant": RESTAURANT,
                                "description": "Test floor"}).insert(ignore_permissions=True).name
    room = frappe.db.get_value("Ren Room", {"floor": floor})
    if not room:
        room = frappe.get_doc({"doctype": "Ren Room", "floor": floor,
                               "description": "Test room"}).insert(ignore_permissions=True).name
    table = frappe.db.get_value("Ren Table", {"room": room, "description": "T-1"})
    if not table:
        table = frappe.get_doc({"doctype": "Ren Table", "room": room, "description": "T-1",
                                "no_of_seats": 4}).insert(ignore_permissions=True).name
    grant_floor(WAITER, floor)
    set_role(WAITER, "Server")
    set_role(CASHIER2, "Cashier")
    return {"company": company, "floor": floor, "room": room, "table": table}


def staff(user, restaurant=None):
    """The person's Ren Staff at the restaurant (created when missing)."""
    restaurant = restaurant or RESTAURANT
    name = frappe.db.get_value("Ren Staff", {"user": user, "restaurant": restaurant})
    if not name:
        name = frappe.get_doc({"doctype": "Ren Staff", "user": user, "restaurant": restaurant, "enabled": 1}) \
            .insert(ignore_permissions=True).name
    return frappe.get_doc("Ren Staff", name)


def grant_floor(user, floor, profile=None):
    """Ren Staff: give `user` a whole floor of its restaurant."""
    restaurant = frappe.db.get_value("Ren Floor", floor, "restaurant")
    doc = staff(user, restaurant)
    if not any(g.object_type == "Ren Floor" and g.object_name == floor for g in doc.restaurant_permissions):
        doc.append("restaurant_permissions", {"object_type": "Ren Floor", "object_name": floor})
        doc.save(ignore_permissions=True)


def grant_station(user, station):
    """Ren Staff: give `user` a production center (a floor doesn't give its stations)."""
    restaurant = frappe.db.get_value("Ren Floor", frappe.db.get_value("Ren Station", station, "floor"), "restaurant")
    doc = staff(user, restaurant)
    if not any(g.object_type == "Ren Station" and g.object_name == station for g in doc.restaurant_permissions):
        doc.append("restaurant_permissions", {"object_type": "Ren Station", "object_name": station})
        doc.save(ignore_permissions=True)


def set_role(user, role, restaurant=None):
    """The person's Ren Role at the restaurant (the test one by default)."""
    from renpos.api.access import install_default_roles
    install_default_roles()
    doc = staff(user, restaurant)
    doc.restaurant_role = role
    doc.save(ignore_permissions=True)


def open_register(user, company):
    for name, start in frappe.get_all(
        "POS Opening Entry",
        filters={"user": user, "pos_profile": PROFILE, "docstatus": 1, "pos_closing_entry": ["in", ["", None]]},
        fields=["name", "period_start_date"], as_list=True,
    ):
        if getdate(start) == getdate(nowdate()):
            return
        frappe.get_doc("POS Opening Entry", name).cancel()  # left open on a previous day
    frappe.get_doc({
        "doctype": "POS Opening Entry", "user": user, "pos_profile": PROFILE, "company": company,
        "period_start_date": now_datetime(), "posting_date": nowdate(),
        "balance_details": [{"mode_of_payment": "Cash", "opening_amount": 0}],
    }).submit()


class TestOrderFlow(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.fx = setup_fixtures()

    def tearDown(self):
        frappe.set_user("Administrator")

    # ── helpers ─────────────────────────────────────
    def new_order(self):
        frappe.set_user(WAITER)
        res = order_api.add_order(self.fx["table"])
        return res["order"]["data"]["name"]

    def push(self, order, item_code, qty=1, plr=None, discount=0, rate=None, identifier=None):
        item = {
            "identifier": identifier or frappe.generate_hash(length=10),
            "item_code": item_code, "qty": qty,
            "price_list_rate": plr if plr is not None else 0,
            "discount_percentage": discount,
            "rate": rate if rate is not None else (plr or 0),
            "item_tax_rate": "{}",
        }
        return order_api.push_item(order, json.dumps(item))

    # ── permissions ─────────────────────────────────
    def test_outsider_is_rejected(self):
        frappe.set_user(OUTSIDER)
        self.assertRaises(frappe.PermissionError, order_api.get_orders, self.fx["table"])
        self.assertRaises(frappe.PermissionError, order_api.add_order, self.fx["table"])

    def test_ren_call_allowlist(self):
        frappe.set_user(WAITER)
        # not allow-listed
        self.assertRaises(frappe.PermissionError, ren_api.call, "User", "Administrator", "delete", "{}")
        # attribute not allowed
        frappe.set_user(MANAGER)
        self.assertRaises(frappe.PermissionError, ren_api.call, "Ren Table", self.fx["table"],
                          "set_attr", json.dumps({"attr": "customer", "value": "x"}))
        # layout change allowed for a manager
        ren_api.call("Ren Table", self.fx["table"], "set_attr",
                     json.dumps({"attr": "data_style", "value": json.dumps({"x": 10, "y": 20})}))

    # ── pricing ─────────────────────────────────────
    def test_server_price_wins(self):
        order = self.new_order()
        res = self.push(order, ITEM_A, qty=2, plr=0.01, rate=0.01)  # tampered price
        self.assertEqual(flt(res["item"]["price_list_rate"]), 10)
        self.assertEqual(flt(res["item"]["rate"]), 10)
        self.assertEqual(flt(res["order"]["data"]["amount"]), 20)

    def test_discount_needs_permission(self):
        from renpos.api.access import ApprovalRequired
        order = self.new_order()  # the waiter's role (Server) allows no discount
        self.assertRaises(ApprovalRequired, self.push, order, ITEM_A, qty=1, plr=10, discount=50, rate=5)
        # without a discount it goes through
        res = self.push(order, ITEM_A, qty=1, plr=10, discount=0, rate=10)
        self.assertEqual(flt(res["item"]["rate"]), 10)

    def test_manager_discount_kept_on_qty_change(self):
        order = self.new_order()
        ident = "keep-disc"
        frappe.set_user(MANAGER)
        self.push(order, ITEM_A, qty=1, plr=10, discount=20, rate=8, identifier=ident)
        frappe.set_user(MANAGER)
        res = self.push(order, ITEM_A, qty=3, plr=10, discount=20, rate=8, identifier=ident)
        frappe.set_user(WAITER)
        # the waiter may lower qty (the discount stays) but more units at 20 % need approval again
        res = self.push(order, ITEM_A, qty=2, plr=10, discount=20, rate=8, identifier=ident)
        self.assertEqual(flt(res["item"]["discount_percentage"]), 20)
        self.assertEqual(flt(res["order"]["data"]["amount"]), 16)
        from renpos.api.access import ApprovalRequired
        self.assertRaises(ApprovalRequired, self.push, order, ITEM_A, qty=4, plr=10, discount=20, rate=8,
                          identifier=ident)

    # ── kitchen / deletion ──────────────────────────
    def test_only_manager_deletes_sent_items(self):
        order = self.new_order()
        self.push(order, ITEM_B, qty=1, plr=2.5, identifier="sent-1")
        order_api.send_order(order)
        self.assertRaises((frappe.PermissionError, frappe.ValidationError), order_api.delete_item, order, "sent-1")
        frappe.set_user(MANAGER)
        order_api.delete_item(order, "sent-1", reason="Kitchen error")

    # ── payment ─────────────────────────────────────
    def test_summary_register_states(self):
        order = self.new_order()
        self.push(order, ITEM_A, qty=1, plr=10)
        # a manager without cashier roles still sees the bill
        frappe.set_user(MANAGER)
        summary = order_api.get_payment_summary(order)
        self.assertEqual(summary["register"]["problem"], "no_permission")
        self.assertEqual(flt(summary["amount_due"]), 10)
        self.assertEqual(frappe.session.user, MANAGER)  # no leaked elevation
        # a cashier without an open register
        frappe.set_user(CASHIER2)
        summary = order_api.get_payment_summary(order)
        self.assertEqual(summary["register"]["problem"], "closed")
        modes = {m["mode_of_payment"]: m["type"] for m in summary["payment_modes"]}
        self.assertEqual(modes.get("Cash"), "Cash")

    def test_full_payment_flow(self):
        frappe.set_user("Administrator")
        open_register(WAITER, self.fx["company"])

        order = self.new_order()
        self.push(order, ITEM_A, qty=2, plr=10)   # 20
        self.push(order, ITEM_B, qty=1, plr=2.5)  # 2.5

        summary = order_api.get_payment_summary(order)
        self.assertIsNone(summary["register"]["problem"])
        due = flt(summary["amount_due"])
        self.assertAlmostEqual(due, 22.5, places=2)

        # not enough
        self.assertRaises(frappe.ValidationError, order_api.process_payment, order,
                          json.dumps([{"mode_of_payment": "Cash", "amount": due - 1}]))
        # card can't be overpaid
        self.assertRaises(frappe.ValidationError, order_api.process_payment, order,
                          json.dumps([{"mode_of_payment": "Credit Card", "amount": due + 5}]))

        res = order_api.process_payment(order, json.dumps([
            {"mode_of_payment": "Credit Card", "amount": 10},
            {"mode_of_payment": "Cash", "amount": 20},
        ]))
        self.assertEqual(res["status"], "Invoiced")
        self.assertEqual(res["invoice_doctype"], summary["invoice_doctype"])
        self.assertAlmostEqual(flt(res["change_amount"]), 30 - due, places=2)

        inv = frappe.get_doc(res["invoice_doctype"], res["invoice"])
        self.assertEqual(inv.docstatus, 1)
        self.assertEqual(inv.owner, WAITER)
        self.assertEqual(len(inv.items), 2)
        self.assertEqual(inv.ignore_pricing_rule, 1)  # ERPNext didn't re-price the order
        self.assertAlmostEqual(flt(inv.grand_total), due, places=2)

        self.assertEqual(frappe.db.get_value("Ren Order", order, "link_invoice"), inv.name)
        # charging twice is refused
        self.assertRaises(frappe.ValidationError, order_api.process_payment, order,
                          json.dumps([{"mode_of_payment": "Cash", "amount": due}]))

    def test_payment_requires_own_register(self):
        frappe.set_user("Administrator")
        open_register(WAITER, self.fx["company"])
        order = self.new_order()
        self.push(order, ITEM_B, qty=1, plr=2.5)
        frappe.set_user(CASHIER2)  # cashier, but no register of their own
        self.assertRaises(frappe.ValidationError, order_api.process_payment, order,
                          json.dumps([{"mode_of_payment": "Cash", "amount": 2.5}]))
        frappe.set_user(MANAGER)   # no cashier role at all
        self.assertRaises(frappe.PermissionError, order_api.process_payment, order,
                          json.dumps([{"mode_of_payment": "Cash", "amount": 2.5}]))

    # ── price list consistency ──────────────────────
    def test_restaurant_price_list_is_used(self):
        frappe.set_user("Administrator")
        if not frappe.db.exists("Price List", "_REN Dinner"):
            frappe.get_doc({"doctype": "Price List", "price_list_name": "_REN Dinner",
                            "selling": 1, "currency": "USD"}).insert(ignore_permissions=True)
        if not frappe.db.exists("Item Price", {"item_code": ITEM_A, "price_list": "_REN Dinner"}):
            frappe.get_doc({"doctype": "Item Price", "item_code": ITEM_A, "price_list": "_REN Dinner",
                            "price_list_rate": 12}).insert(ignore_permissions=True)
        frappe.db.set_value("Ren Restaurant", RESTAURANT, "default_price_list", "_REN Dinner")
        try:
            order = self.new_order()
            res = self.push(order, ITEM_A, qty=1, plr=12)
            self.assertEqual(flt(res["item"]["price_list_rate"]), 12)
            summary = order_api.get_payment_summary(order)
            self.assertAlmostEqual(flt(summary["amount_due"]), 12, places=2)
            # catalog shows the same price
            from renpos.ren_pos.doctype.ren_menu.ren_menu import get_items_for_tree
            items = get_items_for_tree(search=ITEM_A)
            self.assertEqual(flt(items[0]["price_list_rate"]), 12)
        finally:
            frappe.set_user("Administrator")
            frappe.db.set_value("Ren Restaurant", RESTAURANT, "default_price_list", None)

    # ── divide / transfer ───────────────────────────
    def test_divide_order(self):
        order = self.new_order()
        self.push(order, ITEM_A, qty=3, plr=10, identifier="div-a")
        self.push(order, ITEM_B, qty=1, plr=2.5, identifier="div-b")
        res = order_api.divide_order(order, json.dumps({"div-a": {"qty": 1}, "div-b": {"qty": 1}}))
        self.assertAlmostEqual(flt(res["original_order"]["data"]["amount"]), 20, places=2)
        self.assertAlmostEqual(flt(res["new_order"]["data"]["amount"]), 12.5, places=2)
        new = res["new_order"]["data"]["name"]
        self.assertEqual(frappe.db.get_value("Ren Order", new, "table"), self.fx["table"])
        # nothing selected -> error
        self.assertRaises(frappe.ValidationError, order_api.divide_order, order, json.dumps({}))

    def test_transfer_order(self):
        frappe.set_user("Administrator")
        room = frappe.db.get_value("Ren Table", self.fx["table"], "room")
        other = frappe.db.get_value("Ren Table", {"room": room, "description": "T-2"})
        if not other:
            other = frappe.get_doc({"doctype": "Ren Table", "room": room, "description": "T-2",
                                    "no_of_seats": 2}).insert(ignore_permissions=True).name
        order = self.new_order()
        self.push(order, ITEM_B, qty=1, plr=2.5)
        targets = order_api.get_transfer_targets(order)
        tables = [t for f in targets for r in f["rooms"] for t in r["tables"]]
        self.assertTrue(any(t["name"] == other and not t["current"] for t in tables))
        self.assertTrue(any(t["name"] == self.fx["table"] and t["current"] for t in tables))
        order_api.transfer_order(order, other)
        self.assertEqual(frappe.db.get_value("Ren Order", order, "table"), other)
        self.assertRaises(frappe.ValidationError, order_api.transfer_order, order, other)

    # ── regressions from the independent review ─────
    def test_preview_keeps_session(self):
        order = self.new_order()
        self.push(order, ITEM_A, qty=1, plr=10)
        frappe.set_user(MANAGER)
        session = frappe.local.session
        session.sid, session.data = "real-sid-123", frappe._dict(csrf_token="tok")
        form = frappe.local.form_dict
        order_api.get_payment_summary(order)  # builds the preview as Administrator
        self.assertEqual(frappe.session.user, MANAGER)
        self.assertEqual(session.sid, "real-sid-123")
        self.assertEqual(session.data.get("csrf_token"), "tok")
        self.assertIs(frappe.local.form_dict, form)

    def test_paid_order_cannot_be_voided(self):
        frappe.set_user("Administrator")
        open_register(WAITER, self.fx["company"])
        order = self.new_order()
        self.push(order, ITEM_B, qty=1, plr=2.5)
        order_api.process_payment(order, json.dumps([{"mode_of_payment": "Cash", "amount": 2.5}]))
        self.assertRaises(frappe.ValidationError, order_api.delete_order, order)
        self.assertTrue(frappe.db.exists("Ren Order", order))

    def test_coupon_rule_is_not_accepted(self):
        frappe.set_user("Administrator")
        rule = frappe.get_doc({
            "doctype": "Pricing Rule", "title": "_REN coupon 50", "apply_on": "Item Code",
            "items": [{"item_code": ITEM_A}], "selling": 1, "company": self.fx["company"],
            "rate_or_discount": "Discount Percentage", "discount_percentage": 50,
            "coupon_code_based": 1, "price_or_product_discount": "Price",
        }).insert(ignore_permissions=True)
        order = self.new_order()
        item = {"identifier": "coupon-1", "item_code": ITEM_A, "qty": 1, "price_list_rate": 10,
                "discount_percentage": 50, "rate": 5, "item_tax_rate": "{}", "pricing_rule": rule.name}
        res = order_api.push_item(order, json.dumps(item))
        self.assertEqual(flt(res["item"]["rate"]), 10)

    def test_divide_keeps_kitchen_time(self):
        order = self.new_order()
        self.push(order, ITEM_A, qty=2, plr=10, identifier="kt-a")
        order_api.send_order(order)
        sent_at = frappe.db.get_value("Ren Order Item", {"parent": order, "identifier": "kt-a"}, "ordered_time")
        res = order_api.divide_order(order, json.dumps({"kt-a": {"qty": 1}}))
        new = res["new_order"]["data"]["name"]
        self.assertEqual(frappe.db.get_value("Ren Order Item", {"parent": new}, "ordered_time"), sent_at)

    def test_demo_endpoints_need_system_manager(self):
        from renpos.api import demo
        frappe.set_user(WAITER)
        self.assertRaises(frappe.PermissionError, demo.cleanup_demo_data)

    def test_item_without_price_is_rejected(self):
        frappe.set_user("Administrator")
        if not frappe.db.exists("Item", "_REN-NOPRICE"):
            frappe.get_doc({"doctype": "Item", "item_code": "_REN-NOPRICE", "item_name": "_REN-NOPRICE",
                            "item_group": "Products", "stock_uom": "Nos", "is_stock_item": 0,
                            "is_sales_item": 1}).insert(ignore_permissions=True)
        frappe.db.set_value("POS Profile", PROFILE, "allow_rate_change", 0)
        frappe.clear_document_cache("POS Profile", PROFILE)
        order = self.new_order()
        self.assertRaises(frappe.ValidationError, self.push, order, "_REN-NOPRICE", 1, 0)

    def test_transfer_to_table_without_company(self):
        """Tables created before their floor had a restaurant have no company."""
        frappe.set_user("Administrator")
        room = frappe.db.get_value("Ren Table", self.fx["table"], "room")
        bare = frappe.get_doc({"doctype": "Ren Table", "room": room, "description": "T-bare",
                               "no_of_seats": 2}).insert(ignore_permissions=True).name
        frappe.db.set_value("Ren Table", bare, "company", None)
        order = self.new_order()
        self.push(order, ITEM_B, qty=1, plr=2.5)
        order_api.transfer_order(order, bare)
        self.assertEqual(frappe.db.get_value("Ren Order", order, "table"), bare)
        self.assertEqual(frappe.db.get_value("Ren Order", order, "company"), self.fx["company"])
        self.assertEqual(frappe.db.get_value("Ren Table", bare, "company"), self.fx["company"])
