# -*- coding: utf-8 -*-
"""Permissions: roles, tables, other people's orders, manager PIN approvals, audit, legacy holes."""

import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from renpos.api import access
from renpos.api import order as order_api
from renpos.api.access import ApprovalRequired
from renpos.tests.test_order_flow import (
    CASHIER2, ITEM_A, MANAGER, PROFILE, RESTAURANT, WAITER, set_role, setup_fixtures,
)

MANAGER_PIN = "482913"


class TestAccess(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.fx = setup_fixtures()
        access.install_default_roles()
        frappe.set_user(MANAGER)
        access.set_pin(MANAGER_PIN)
        frappe.set_user("Administrator")

    def setUp(self):
        # each test starts with a free table (Own tables: an occupied table belongs to its server)
        frappe.db.sql("""UPDATE `tabRen Order` SET status = 'Cancelled'
            WHERE `table` = %s AND status NOT IN ('Invoiced', 'Cancelled')""", self.fx["table"])

    def tearDown(self):
        frappe.set_user("Administrator")
        set_role(WAITER, "Server")
        set_role(CASHIER2, "Cashier")
        frappe.cache.delete_keys("ren_pin_attempts")

    def new_order(self, user=WAITER):
        frappe.set_user(user)
        return order_api.add_order(self.fx["table"])["order"]["data"]["name"]

    def push(self, order, ident, discount=0, rate=10, qty=1):
        return order_api.push_item(order, json.dumps({
            "identifier": ident, "item_code": ITEM_A, "qty": qty, "price_list_rate": 10,
            "discount_percentage": discount, "rate": rate, "item_tax_rate": "{}"}))

    def pin(self, action, amount=None, pin=MANAGER_PIN, reference=None):
        return access.approve(action, pin, amount=amount, reference=reference)["approval"]

    # ── roles ──

    def test_discount_limit_and_pin_approval(self):
        set_role(WAITER, "Bartender")  # up to 10 %
        order = self.new_order()
        self.assertEqual(flt(self.push(order, "d-10", discount=10, rate=9)["item"]["discount_percentage"]), 10)
        self.assertRaises(ApprovalRequired, self.push, order, "d-20", discount=20, rate=8)
        token = self.pin("discount", amount=20)
        frappe.form_dict.approval = token
        try:
            self.assertEqual(flt(self.push(order, "d-20", discount=20, rate=8)["item"]["discount_percentage"]), 20)
            # one-time token
            self.assertRaises(ApprovalRequired, self.push, order, "d-20b", discount=20, rate=8)
        finally:
            frappe.form_dict.pop("approval", None)
        frappe.set_user("Administrator")
        log = frappe.get_all("Ren Audit Log", filters={"reference_name": order, "action": "approved:discount"},
                             fields=["user", "approved_by", "amount"])
        self.assertEqual((log[0].user, log[0].approved_by, log[0].amount), (WAITER, MANAGER, 20))

    def test_token_is_bound_to_the_action_and_amount(self):
        order = self.new_order()
        token = self.pin("discount", amount=5)
        frappe.form_dict.approval = token
        try:
            self.assertRaises(ApprovalRequired, self.push, order, "b-1", discount=30, rate=7)  # more than approved
        finally:
            frappe.form_dict.pop("approval", None)
        self.assertRaises(frappe.PermissionError, access.approve, "discount", "111111")  # wrong PIN
        self.assertRaises(frappe.ValidationError, access.approve, "nonsense", MANAGER_PIN)

    def test_void_sent_item_needs_role_or_pin(self):
        from renpos.api import voids
        voids.install_default_reasons()
        order = self.new_order()
        self.push(order, "v-1")
        order_api.send_order(order)
        self.assertRaises(ApprovalRequired, order_api.delete_item, order, "v-1", reason="Kitchen error")
        frappe.form_dict.approval = self.pin("void_sent_items", amount=10, reference=order)
        try:
            order_api.delete_item(order, "v-1", reason="Kitchen error")
        finally:
            frappe.form_dict.pop("approval", None)

    def test_price_change(self):
        order = self.new_order()
        self.assertRaises(ApprovalRequired, self.push, order, "p-1", discount=0, rate=4)  # custom rate
        frappe.set_user("Administrator")
        frappe.db.set_value("Ren Role", "Server", "change_price", 1)
        frappe.clear_document_cache("Ren Role", "Server")
        try:
            frappe.set_user(WAITER)
            self.assertEqual(flt(self.push(order, "p-1", discount=0, rate=4)["item"]["rate"]), 4)
        finally:
            frappe.set_user("Administrator")
            frappe.db.set_value("Ren Role", "Server", "change_price", 0)
            frappe.clear_document_cache("Ren Role", "Server")

    def test_token_bound_to_the_order_and_void_amount(self):
        from renpos.api import voids
        voids.install_default_reasons()
        a, b = self.new_order(), self.new_order()
        for o in (a, b):
            self.push(o, f"tb-{o}", qty=1)
            self.push(o, f"tb2-{o}", qty=5)
            order_api.send_order(o)
        token = self.pin("void_sent_items", amount=10, reference=a)  # approves voiding up to $10 on order a
        frappe.form_dict.approval = token
        try:
            self.assertRaises(ApprovalRequired, order_api.delete_item, b, f"tb-{b}", reason="Kitchen error")
            self.assertRaises(ApprovalRequired, order_api.delete_item, a, f"tb2-{a}", reason="Kitchen error")  # $50
            order_api.delete_item(a, f"tb-{a}", reason="Kitchen error")
        finally:
            frappe.form_dict.pop("approval", None)

    def test_more_units_at_an_approved_discount_need_it_again(self):
        order = self.new_order()
        frappe.form_dict.approval = self.pin("discount", amount=50, reference=order)
        try:
            self.push(order, "q-1", discount=50, rate=5, qty=1)
        finally:
            frappe.form_dict.pop("approval", None)
        self.push(order, "q-1", discount=50, rate=5, qty=1)  # same line, notes etc.: fine
        self.assertRaises(ApprovalRequired, self.push, order, "q-1", discount=50, rate=5, qty=20)

    def test_staff_pricing_rules_are_ignored(self):
        frappe.set_user("Administrator")
        rule = frappe.get_doc({
            "doctype": "Pricing Rule", "title": "_REN staff rule", "apply_on": "Item Code",
            "items": [{"item_code": ITEM_A}], "selling": 1, "company": self.fx["company"],
            "rate_or_discount": "Rate", "rate": 0.01, "price_or_product_discount": "Price",
        }).insert(ignore_permissions=True)
        frappe.db.set_value("Pricing Rule", rule.name, "modified_by", CASHIER2, update_modified=False)
        try:
            order = self.new_order()
            res = order_api.push_item(order, json.dumps({
                "identifier": "pr-1", "item_code": ITEM_A, "qty": 1, "price_list_rate": 0.01, "rate": 0.01,
                "discount_percentage": 0, "item_tax_rate": "{}", "pricing_rule": rule.name}))
            self.assertEqual(flt(res["item"]["rate"]), 10)
        finally:
            frappe.set_user("Administrator")
            frappe.delete_doc("Pricing Rule", rule.name, force=True, ignore_permissions=True)

    def test_managers_cannot_take_over_admin_pins(self):
        frappe.set_user(MANAGER)
        self.assertRaises(frappe.PermissionError, access.set_pin, "123456", "Administrator")

    # ── tables & orders ──

    def test_tables_of_other_floors_and_restaurants(self):
        frappe.set_user("Administrator")
        floor2 = frappe.db.get_value("Ren Floor", {"restaurant": RESTAURANT, "description": "Access floor"}) \
            or frappe.get_doc({"doctype": "Ren Floor", "restaurant": RESTAURANT,
                               "description": "Access floor"}).insert(ignore_permissions=True).name
        room2 = frappe.db.get_value("Ren Room", {"floor": floor2}) or frappe.get_doc(
            {"doctype": "Ren Room", "floor": floor2, "description": "Access room"}).insert(ignore_permissions=True).name
        t2 = frappe.db.get_value("Ren Table", {"room": room2}) or frappe.get_doc(
            {"doctype": "Ren Table", "room": room2, "description": "A-1"}).insert(ignore_permissions=True).name
        frappe.set_user(WAITER)  # granted floor 1 only
        self.assertRaises(frappe.PermissionError, order_api.add_order, t2)
        self.assertRaises(frappe.PermissionError, order_api.get_orders, t2)
        # a cashier works every table
        frappe.set_user(CASHIER2)
        order_api.get_orders(t2)

    def test_other_peoples_orders(self):
        mine = self.new_order(CASHIER2)  # the cashier opens an order on the waiter's table
        frappe.set_user(WAITER)
        # Server: sees it, but working on it needs a PIN
        self.assertIn(mine, [o["data"]["name"] for o in order_api.get_orders(self.fx["table"])["orders"]])
        self.assertRaises(ApprovalRequired, self.push, mine, "o-1")
        frappe.form_dict.approval = self.pin("operate_others_orders")
        try:
            self.push(mine, "o-1")
        finally:
            frappe.form_dict.pop("approval", None)
        # a role that doesn't see other people's orders
        frappe.set_user("Administrator")
        frappe.db.set_value("Ren Role", "Server", "view_others_orders", 0)
        frappe.clear_document_cache("Ren Role", "Server")
        try:
            frappe.set_user(WAITER)
            self.assertNotIn(mine, [o["data"]["name"] for o in order_api.get_orders(self.fx["table"])["orders"]])
            self.assertRaises(frappe.PermissionError, order_api.get_items, mine)
        finally:
            frappe.set_user("Administrator")
            frappe.db.set_value("Ren Role", "Server", "view_others_orders", 1)
            frappe.clear_document_cache("Ren Role", "Server")

    def test_table_service_policy(self):
        """Own tables: someone else's table needs the role or a PIN; Team service: anyone who works it."""
        theirs = self.new_order(CASHIER2)
        frappe.set_user(WAITER)  # Server role: no "work on other people's orders"
        self.assertEqual(access.role_of(pos_profile=PROFILE).table_service, "Own tables")
        self.assertRaises(ApprovalRequired, order_api.add_order, self.fx["table"])
        self.assertRaises(ApprovalRequired, self.push, theirs, "ts-1")
        frappe.form_dict.approval = self.pin("operate_others_orders", reference=self.fx["table"])
        try:
            self.assertTrue(order_api.add_order(self.fx["table"])["order"]["data"]["name"])
        finally:
            frappe.form_dict.pop("approval", None)
        frappe.set_user("Administrator")
        frappe.db.set_value("Ren Restaurant", RESTAURANT, "table_service", "Team service")
        try:
            frappe.set_user(WAITER)
            self.assertTrue(access.can("operate_others_orders", PROFILE))
            self.assertTrue(order_api.add_order(self.fx["table"])["order"]["data"]["name"])
            self.push(theirs, "ts-2")
        finally:
            frappe.set_user("Administrator")
            frappe.db.set_value("Ren Restaurant", RESTAURANT, "table_service", "Own tables")

    def test_orders_change_only_through_the_api(self):
        order = self.new_order()
        self.push(order, "api-1")
        frappe.set_user(WAITER)
        doc = frappe.get_doc("Ren Order", order)
        doc.entry_items[0].rate = 0.01
        self.assertRaises(frappe.PermissionError, doc.save)  # waiters can't write orders directly
        frappe.set_user(MANAGER)
        frappe.flags.ren_order_api = False
        doc = frappe.get_doc("Ren Order", order)
        doc.entry_items[0].rate = 0.01
        self.assertRaises(frappe.ValidationError, doc.save)  # not even managers, from the desk
        doc.reload()
        doc.notes = "window seat"
        doc.save()  # notes are fine

    def test_closed_pos_profile_and_bookings_of_other_restaurants(self):
        from renpos.api.guards import check_billing_profile, check_pos_profile_access
        from renpos.api import booking
        frappe.set_user("Administrator")
        if frappe.db.exists("POS Profile", "_REN Empty Profile"):
            frappe.delete_doc("POS Profile", "_REN Empty Profile", force=True, ignore_permissions=True)
        empty = frappe.copy_doc(frappe.get_doc("POS Profile", PROFILE))
        empty.set("applicable_for_users", [])
        empty.insert(ignore_permissions=True, set_name="_REN Empty Profile")
        try:
            frappe.set_user(WAITER)
            # a profile of his restaurant: usable for orders, but he isn't listed in it to charge
            check_pos_profile_access(empty.name)
            self.assertRaises(frappe.PermissionError, check_billing_profile, empty.name)
            self.assertRaises(frappe.PermissionError, booking.get_day, None, "_Some Other Restaurant")
        finally:
            frappe.set_user("Administrator")
            frappe.delete_doc("POS Profile", empty.name, force=True, ignore_permissions=True)

    def test_access_comes_from_the_restaurant_staff(self):
        """Ren Staff gives the role and the access; the POS Profile is only for charging."""
        from renpos.api.guards import (billing_profiles, check_billing_profile, current_pos_profile,
                                       current_restaurant)
        from renpos.tests.test_order_flow import _ensure_user, staff
        frappe.set_user("Administrator")
        runner = "_rm_runner@example.com"
        _ensure_user(runner, ["Restaurant User"])
        # not staff anywhere: no restaurant
        frappe.set_user(runner)
        self.assertIsNone(current_restaurant())
        self.assertRaises(frappe.PermissionError, order_api.add_order, self.fx["table"])

        # staff of the restaurant with the floor, but in no POS Profile: takes orders, doesn't charge
        frappe.set_user("Administrator")
        doc = staff(runner)
        doc.restaurant_role = "Server"
        doc.set("restaurant_permissions", [{"object_type": "Ren Floor", "object_name": self.fx["floor"]}])
        doc.save(ignore_permissions=True)
        try:
            frappe.set_user(runner)
            self.assertEqual(current_restaurant(), RESTAURANT)
            self.assertEqual(billing_profiles(), [])
            self.assertTrue(current_pos_profile())  # the restaurant's own, for prices
            order = order_api.add_order(self.fx["table"])["order"]["data"]["name"]
            self.assertTrue(order)
            self.assertEqual(frappe.db.get_value("Ren Order", order, "restaurant"), RESTAURANT)
            self.assertRaises(frappe.PermissionError, check_billing_profile, PROFILE)
            ctx = access.my_context()
            self.assertEqual(ctx["restaurant"]["name"], RESTAURANT)
            self.assertEqual(ctx["role"]["source"], "staff")
            self.assertEqual(ctx["staff"][0]["grants"][0]["name"], self.fx["floor"])
            self.assertEqual(ctx["billing_profiles"], [])

            # without the floor, the table is out of reach
            frappe.set_user("Administrator")
            doc.reload()
            doc.set("restaurant_permissions", [])
            doc.save(ignore_permissions=True)
            frappe.set_user(runner)
            self.assertRaises(frappe.PermissionError, order_api.get_orders, self.fx["table"])

            # a cashier is listed in the POS Profile and charges with it
            frappe.set_user(WAITER)
            self.assertIn(PROFILE, billing_profiles())
            check_billing_profile(PROFILE)
        finally:
            frappe.set_user("Administrator")
            frappe.delete_doc("Ren Staff", doc.name, force=True, ignore_permissions=True)

    def test_charged_with_the_cashiers_profile(self):
        """An order taken with one POS Profile is charged with the cashier's (their register)."""
        from renpos.api.invoicing import billing_profile_for, build_invoice_preview
        frappe.set_user("Administrator")
        bar = "_REN Bar POS"
        if frappe.db.exists("POS Profile", bar):
            frappe.delete_doc("POS Profile", bar, force=True, ignore_permissions=True)
        doc = frappe.copy_doc(frappe.get_doc("POS Profile", PROFILE))
        doc.set("applicable_for_users", [{"user": CASHIER2, "default": 1}])
        doc.insert(ignore_permissions=True, set_name=bar)
        frappe.db.set_value("POS Profile User", {"parent": PROFILE, "user": CASHIER2}, "default", 0)
        try:
            order = frappe.get_doc("Ren Order", self.new_order())  # taken by the waiter with his profile
            self.assertEqual(order.pos_profile, PROFILE)
            frappe.set_user(CASHIER2)
            self.assertEqual(billing_profile_for(order), bar)
            self.push(order.name, "bar-1")
            frappe.set_user(CASHIER2)
            self.assertEqual(build_invoice_preview(frappe.get_doc("Ren Order", order.name)).pos_profile, bar)
        finally:
            frappe.set_user("Administrator")
            frappe.db.set_value("POS Profile User", {"parent": PROFILE, "user": CASHIER2}, "default", 1)
            frappe.delete_doc("POS Profile", bar, force=True, ignore_permissions=True)

    # ── PINs, staff ──

    def test_pins(self):
        frappe.set_user(WAITER)
        self.assertRaises(frappe.ValidationError, access.set_pin, "12")
        access.set_pin("700700")  # PINs aren't unique (telling would reveal other people's)
        self.assertTrue(access.has_pin())
        # nobody approves themselves
        self.assertRaises(frappe.PermissionError, access.approve, "discount", "700700", 5)
        self.assertRaises(frappe.PermissionError, access.set_pin, "123456", CASHIER2)  # not someone else's
        frappe.set_user(MANAGER)
        access.set_pin("700701", WAITER)  # managers can reset someone's PIN

    def test_clock_in_requirement(self):
        from renpos.api import staff
        frappe.db.set_single_value("Ren Settings", "require_clock_in", 1)
        try:
            frappe.set_user(WAITER)
            staff.clock_out()
            self.assertRaises(frappe.ValidationError, order_api.add_order, self.fx["table"])
            staff.clock_in()
            order_api.add_order(self.fx["table"])
            self.assertTrue(staff.get_shift()["clocked_in"])
            staff.clock_out()
        finally:
            frappe.set_user("Administrator")
            frappe.db.set_single_value("Ren Settings", "require_clock_in", 0)

    def test_pin_login_needs_a_registered_terminal(self):
        from renpos.api import staff
        frappe.db.set_single_value("Ren Settings", "allow_pin_login", 1)
        try:
            frappe.set_user(MANAGER)
            token = staff.register_terminal("Bar iPad", PROFILE)["token"]
            frappe.set_user("Guest")
            self.assertTrue(staff.terminal_info(token)["valid"])
            self.assertFalse(staff.terminal_info("nope")["valid"])
            self.assertRaises(frappe.PermissionError, staff.pin_login, WAITER, "700701", "nope")
            self.assertRaises(frappe.AuthenticationError, staff.pin_login, WAITER, "999999", token)
            # never an administrator / system manager
            self.assertRaises(frappe.AuthenticationError, staff.pin_login, "Administrator", MANAGER_PIN, token)
            self.assertNotIn("Administrator", [s["user"] for s in staff.terminal_info(token)["staff"]])
        finally:
            frappe.set_user("Administrator")
            frappe.db.set_single_value("Ren Settings", "allow_pin_login", 0)

    # ── legacy holes ──

    def test_legacy_endpoints_are_gone(self):
        import importlib.util
        # the old page backend and Desk Forms (with their SQL-injectable endpoints) were removed
        self.assertIsNone(importlib.util.find_spec(
            "renpos.ren_pos.page.restaurant_manage"))
        self.assertIsNone(importlib.util.find_spec("renpos.ren_pos.doctype.desk_form"))
        frappe.set_user(WAITER)


NEW_STAFF = "ren-newstaff@test.local"


class TestStaffSetup(FrappeTestCase):
    """What Ren Staff gives: areas narrow "every table", stations one by one, the Kitchen role, charging."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.fx = setup_fixtures()
        access.install_default_roles()
        if frappe.db.exists("Ren Role", "Kitchen"):
            frappe.delete_doc("Ren Role", "Kitchen", force=True, ignore_permissions=True)
        access.insert_default_role("Kitchen")
        if not frappe.db.exists("User", NEW_STAFF):
            frappe.get_doc({"doctype": "User", "email": NEW_STAFF, "first_name": "New", "send_welcome_email": 0,
                            "roles": [{"role": "Restaurant User"}]}).insert(ignore_permissions=True)

    def setUp(self):
        frappe.set_user("Administrator")
        for name in frappe.get_all("Ren Staff", filters={"user": NEW_STAFF}, pluck="name"):
            frappe.delete_doc("Ren Staff", name, force=True, ignore_permissions=True)
        frappe.get_doc("User", NEW_STAFF).remove_roles("Accounts User", "Sales Manager")
        frappe.db.delete("POS Profile User", {"parent": PROFILE, "user": NEW_STAFF})

    def tearDown(self):
        self.setUp()

    def _staff(self, role=None, grants=()):
        return frappe.get_doc({"doctype": "Ren Staff", "user": NEW_STAFF, "restaurant": RESTAURANT, "enabled": 1,
                               "restaurant_role": role,
                               "restaurant_permissions": [{"object_type": t, "object_name": n} for t, n in grants],
                               }).insert(ignore_permissions=True)

    def test_every_table_is_narrowed_by_the_assigned_areas(self):
        self._staff("Cashier")
        frappe.set_user(NEW_STAFF)
        self.assertIsNone(access.user_tables())  # nothing assigned: the whole restaurant
        frappe.set_user("Administrator")
        doc = frappe.get_doc("Ren Staff", {"user": NEW_STAFF})
        doc.append("restaurant_permissions", {"object_type": "Ren Room", "object_name": self.fx["room"]})
        doc.save(ignore_permissions=True)
        frappe.set_user(NEW_STAFF)
        tables = access.user_tables()
        self.assertIsNotNone(tables)
        self.assertIn(self.fx["table"], tables)

    def test_a_cook_gets_the_kitchen_role(self):
        from renpos.tests.test_kitchen import make_station
        station = make_station(self.fx["floor"], grant_to=None)
        doc = self._staff(grants=[("Ren Station", station)])
        self.assertEqual(doc.restaurant_role, "Kitchen")
        frappe.set_user(NEW_STAFF)
        self.assertFalse(access.can("take_payments"))
        self.assertEqual(access.user_tables(), set())
        # no tables: no phone orders (no "Delivery" button) and no host stand
        from renpos.api import booking, delivery
        self.assertFalse(delivery.takes_phone_orders())
        self.assertRaises(frappe.PermissionError, delivery.new_order, "02128", address_line="1 Main St")
        self.assertRaises(frappe.PermissionError, booking.get_day)

    def test_charging_needs_erpnext_rights_and_a_profile(self):
        from renpos.api import staff as staff_api
        doc = self._staff("Cashier")
        gaps = staff_api.charging_gaps(NEW_STAFF, RESTAURANT)
        self.assertEqual(len(gaps), 2)
        # the test waiter already charges: nothing missing
        self.assertEqual(staff_api.charging_gaps(WAITER, RESTAURANT), [])
        staff_api.enable_charging(doc.name)
        self.assertEqual(staff_api.charging_gaps(NEW_STAFF, RESTAURANT), [])
        # only a System Manager gives accounting roles
        frappe.set_user(MANAGER)
        self.assertRaises(frappe.PermissionError, staff_api.enable_charging, doc.name)


class TestConfigSync(FrappeTestCase):
    """Setup changes tell the open POS screens to reload (api/sync.py)."""

    def test_setup_changes_publish_ren_config(self):
        from unittest.mock import patch
        frappe.set_user("Administrator")
        setup_fixtures()
        sent = []
        with patch("frappe.publish_realtime", side_effect=lambda event, message=None, **kw: sent.append(
                (event, (message or {}).get("doctype"), kw.get("user")))):
            role = frappe.get_doc("Ren Role", "Server")
            role.save(ignore_permissions=True)
            staff = frappe.get_doc("Ren Staff", {"user": WAITER, "restaurant": RESTAURANT})
            staff.save(ignore_permissions=True)
        self.assertIn(("ren_config", "Ren Role", None), sent)
        # a person's access only goes to that person
        self.assertIn(("ren_config", "Ren Staff", WAITER), sent)
