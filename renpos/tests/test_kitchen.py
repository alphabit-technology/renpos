# -*- coding: utf-8 -*-
"""
Production centers (kitchen display) API tests.

    bench --site <site> run-tests --module renpos.tests.test_kitchen
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from renpos.api import kitchen as kitchen_api
from renpos.api import order as order_api
from renpos.api import voids as voids_api
from renpos.tests.test_order_flow import (
    CASHIER2, MANAGER, WAITER, ITEM_A, ITEM_B, RESTAURANT, _ensure_item, grant_station, setup_fixtures,
)

R = "-" + frappe.generate_hash(length=6)  # unique line identifiers per run
FOOD = "_REN-STEAK"
DRINK = "_REN-COFFEE"


def make_station(floor, name="_REN Kitchen", flow=("Sent", "Processing", "Completed"), groups=("Products",),
                 grouped=0, grant_to=WAITER):
    """A production center on `floor`, given to the waiter (stations are given one by one)."""
    name = _station_named(floor, name, flow, groups, grouped)
    if grant_to:
        grant_station(grant_to, name)
    return name


def _station_named(floor, name, flow, groups, grouped):
    existing = frappe.db.get_value("Ren Station", {"description": name})
    if existing:
        return existing
    return frappe.get_doc({
        "doctype": "Ren Station",
        "description": name,
        "floor": floor,
        "group_items_by_order": grouped,
        "production_center_group": [{"item_group": g} for g in groups],
        "status_flow": [{"status": s} for s in flow],
    }).insert(ignore_permissions=True).name


def ensure_group(name):
    if not frappe.db.exists("Item Group", name):
        frappe.get_doc({"doctype": "Item Group", "item_group_name": name,
                        "parent_item_group": "All Item Groups"}).insert(ignore_permissions=True)
    return name


def ensure_grouped_item(code, group):
    _ensure_item(code, 0)
    frappe.db.set_value("Item", code, "item_group", group)


def ticket_of(queue, order):
    return [t for t in queue["tickets"] if t["order"] == order]


class KitchenCase(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.fx = setup_fixtures()
        cls.station = make_station(cls.fx["floor"])
        ensure_grouped_item(FOOD, ensure_group("_REN Food"))
        ensure_grouped_item(DRINK, ensure_group("_REN Drinks"))

    def tearDown(self):
        frappe.set_user("Administrator")

    def new_order(self, *lines, send=True):
        """lines: (identifier, item_code)"""
        frappe.set_user(WAITER)
        order = order_api.add_order(self.fx["table"])["order"]["data"]["name"]
        self.push(order, *lines)
        if send:
            order_api.send_order(order)
        return order

    def push(self, order, *lines):
        frappe.set_user(WAITER)
        for ident, code in lines:
            order_api.push_item(order, json.dumps({
                "identifier": ident, "item_code": code, "qty": 1,
                "price_list_rate": 0, "discount_percentage": 0, "rate": 0, "item_tax_rate": "{}",
            }))

    def status(self, ident):
        return frappe.db.get_value("Ren Order Item", {"identifier": ident}, "status")


class TestKitchen(KitchenCase):
    def test_queue_and_advance(self):
        frappe.set_user(WAITER)
        order = self.new_order((("k-a" + R), ITEM_A), (("k-b" + R), ITEM_B), send=False)

        # nothing at the center until the order is sent
        self.assertFalse(ticket_of(kitchen_api.get_station_queue(self.station), order))

        order_api.send_order(order)
        q = kitchen_api.get_station_queue(self.station)
        (ticket,) = ticket_of(q, order)
        self.assertEqual({i["identifier"] for i in ticket["items"]}, {("k-a" + R), ("k-b" + R)})
        self.assertEqual(ticket["items"][0]["status"], "Sent")
        self.assertEqual(ticket["items"][0]["next_status"], "Processing")
        # the button shows the action of the status it leads to
        # current status shown as its message, the button with the action that leads to the next one
        self.assertEqual(ticket["items"][0]["message"], "Waiting")
        self.assertEqual(ticket["items"][0]["action"], "Start")
        self.assertEqual(ticket["table"], self.fx["table"])
        self.assertEqual(ticket["round"], 1)
        self.assertEqual(q["station"]["flow"], ["Sent", "Processing", "Completed"])

        self.assertEqual(kitchen_api.advance(self.station, ("k-a" + R))["status"], "Processing")
        self.assertEqual(kitchen_api.advance(self.station, ("k-a" + R))["status"], "Completed")
        # completed lines leave the queue and can't advance further
        (ticket,) = ticket_of(kitchen_api.get_station_queue(self.station), order)
        self.assertEqual([i["identifier"] for i in ticket["items"]], [("k-b" + R)])
        self.assertRaises(kitchen_api.KitchenConflict, kitchen_api.advance, self.station, ("k-a" + R))

        # the waiter's order shows the kitchen status
        items = {i["identifier"]: i for i in order_api.get_items(order)["items"]}
        self.assertEqual(items[("k-a" + R)]["status"], "Completed")

        # every move is logged
        logs = frappe.get_all("Ren Kitchen Status Log", filters={"identifier": ("k-a" + R)},
                              fields=["from_status", "to_status", "station", "user"], order_by="creation")
        self.assertEqual([(l.from_status, l.to_status) for l in logs],
                         [("Sent", "Processing"), ("Processing", "Completed")])
        self.assertEqual({(l.station, l.user) for l in logs}, {(self.station, WAITER)})

    def test_floor_summary_counts_tickets_by_status(self):
        def summary():
            s = kitchen_api.get_floor_summary(self.fx["floor"])["stations"][self.station]
            return s["tickets"], {x["status"]: x["count"] for x in s["statuses"]}

        frappe.set_user(WAITER)
        tickets0, by0 = summary()
        self.new_order((("s-a" + R), ITEM_A), (("s-b" + R), ITEM_B))
        tickets1, by1 = summary()
        self.assertEqual(tickets1, tickets0 + 1)
        self.assertEqual(by1.get("Sent", 0), by0.get("Sent", 0) + 1)

        # a ticket counts in its earliest status: one line ahead doesn't move it
        kitchen_api.advance(self.station, "s-a" + R)
        self.assertEqual(summary()[1].get("Sent", 0), by0.get("Sent", 0) + 1)
        kitchen_api.advance(self.station, "s-b" + R)
        _, by2 = summary()
        self.assertEqual(by2.get("Sent", 0), by0.get("Sent", 0))
        self.assertEqual(by2.get("Processing", 0), by0.get("Processing", 0) + 1)

    def test_expected_status_stops_double_taps(self):
        self.new_order((("k-dbl" + R), ITEM_A))
        frappe.set_user(WAITER)
        kitchen_api.advance(self.station, ("k-dbl" + R), expected="Sent")
        # a second screen still showing "Sent" taps too: nothing moves
        self.assertRaises(kitchen_api.KitchenConflict, kitchen_api.advance, self.station, ("k-dbl" + R), expected="Sent")
        self.assertEqual(self.status(("k-dbl" + R)), "Processing")

    def test_new_round_is_a_new_ticket(self):
        order = self.new_order((("r-1" + R), ITEM_A))
        frappe.set_user(WAITER)
        kitchen_api.advance(self.station, ("r-1" + R))
        kitchen_api.advance(self.station, ("r-1" + R))  # round 1 done
        self.push(order, (("r-2" + R), ITEM_B))
        order_api.send_order(order)
        (ticket,) = ticket_of(kitchen_api.get_station_queue(self.station), order)
        self.assertEqual([i["identifier"] for i in ticket["items"]], [("r-2" + R)])
        self.assertEqual(ticket["round"], 2)

        # two rounds waiting at the same time: two tickets
        self.push(order, (("r-3" + R), ITEM_A))
        order_api.send_order(order)
        tickets = ticket_of(kitchen_api.get_station_queue(self.station), order)
        self.assertEqual([t["round"] for t in tickets], [2, 3])
        self.assertEqual(len({t["key"] for t in tickets}), 2)

    def test_order_tabs_counts(self):
        order = self.new_order((("cnt-1" + R), ITEM_A), (("cnt-2" + R), ITEM_B))
        self.push(order, (("cnt-3" + R), ITEM_A))
        frappe.set_user(WAITER)
        tab = [o["data"] for o in order_api.get_orders(self.fx["table"])["orders"] if o["data"]["name"] == order][0]
        self.assertEqual((tab["items_count"], tab["pending_count"]), (3, 1))
        data = order_api.get_items(order)["order"]["data"]
        self.assertEqual((data["items_count"], data["pending_count"]), (3, 1))

    def test_stations_listed(self):
        frappe.set_user(WAITER)
        names = [s["name"] for s in kitchen_api.get_stations()]
        self.assertIn(self.station, names)


class TestGroupedCenters(KitchenCase):
    def test_grouped_ticket_moves_only_its_lines(self):
        frappe.set_user("Administrator")
        kitchen = make_station(self.fx["floor"], "_REN Grill (grouped)", groups=("_REN Food",), grouped=1)
        bar = make_station(self.fx["floor"], "_REN Bar (grouped)", groups=("_REN Drinks",), grouped=1)
        order = self.new_order((("g-food" + R), FOOD), (("g-drink" + R), DRINK))
        frappe.set_user(WAITER)

        (bar_ticket,) = ticket_of(kitchen_api.get_station_queue(bar), order)
        self.assertEqual([i["identifier"] for i in bar_ticket["items"]], [("g-drink" + R)])
        self.assertEqual(bar_ticket["next_status"], "Processing")

        # the bar dispatches its ticket twice: only the drink moves
        kitchen_api.advance(bar, ticket=bar_ticket["key"], expected="Sent")
        kitchen_api.advance(bar, ticket=bar_ticket["key"], expected="Processing")
        self.assertEqual(self.status(("g-drink" + R)), "Completed")
        self.assertEqual(self.status(("g-food" + R)), "Sent")
        self.assertEqual(frappe.db.get_value("Ren Order", order, "status"), "Sent")
        self.assertFalse(ticket_of(kitchen_api.get_station_queue(bar), order))

        # the kitchen still has its food ticket
        (k_ticket,) = ticket_of(kitchen_api.get_station_queue(kitchen), order)
        self.assertEqual([i["identifier"] for i in k_ticket["items"]], [("g-food" + R)])
        self.assertEqual(k_ticket["status"], "Sent")

        # a grouped center never shows lines that weren't sent
        self.push(order, (("g-unsent" + R), FOOD))
        (k_ticket,) = ticket_of(kitchen_api.get_station_queue(kitchen), order)
        self.assertNotIn(("g-unsent" + R), [i["identifier"] for i in k_ticket["items"]])

    def test_ticket_moves_its_earliest_lines(self):
        frappe.set_user("Administrator")
        kitchen = make_station(self.fx["floor"], "_REN Grill (grouped)", groups=("_REN Food",), grouped=1)
        order = self.new_order((("e-1" + R), FOOD), (("e-2" + R), FOOD))
        frappe.set_user(WAITER)
        kitchen_api.advance(kitchen, ("e-1" + R))  # a single line can still be moved
        (t,) = ticket_of(kitchen_api.get_station_queue(kitchen), order)
        self.assertEqual(t["status"], "Sent")
        kitchen_api.advance(kitchen, ticket=t["key"], expected="Sent")
        self.assertEqual((self.status(("e-1" + R)), self.status(("e-2" + R))), ("Processing", "Processing"))

    def test_chained_centers_share_the_line_status(self):
        frappe.set_user("Administrator")
        cafe = make_station(self.fx["floor"], "_REN Cafeteria", flow=("Sent", "Delivering"), groups=("_REN Drinks",))
        salon = make_station(self.fx["floor"], "_REN Dining room", flow=("Delivering", "Delivered"),
                             groups=("_REN Drinks",))
        order = self.new_order((("c-coffee" + R), DRINK))
        frappe.set_user(WAITER)
        self.assertTrue(ticket_of(kitchen_api.get_station_queue(cafe), order))
        self.assertFalse(ticket_of(kitchen_api.get_station_queue(salon), order))

        kitchen_api.advance(cafe, ("c-coffee" + R), expected="Sent")
        self.assertFalse(ticket_of(kitchen_api.get_station_queue(cafe), order))
        (t,) = ticket_of(kitchen_api.get_station_queue(salon), order)
        self.assertEqual(t["items"][0]["status"], "Delivering")

        kitchen_api.advance(salon, ("c-coffee" + R), expected="Delivering")
        self.assertEqual(self.status(("c-coffee" + R)), "Delivered")
        self.assertFalse(ticket_of(kitchen_api.get_station_queue(salon), order))


class TestCenterAccess(KitchenCase):
    def test_access_comes_from_the_assigned_stations(self):
        frappe.set_user("Administrator")
        other_floor = frappe.db.get_value("Ren Floor", {"restaurant": RESTAURANT, "description": "Test floor 2"}) \
            or frappe.get_doc({"doctype": "Ren Floor", "restaurant": RESTAURANT,
                               "description": "Test floor 2"}).insert(ignore_permissions=True).name
        elsewhere = make_station(other_floor, "_REN Pastry (floor 2)", grant_to=None)
        same_floor = make_station(self.fx["floor"], "_REN Not given", grant_to=None)

        # the waiter has the stations given to them; their floor doesn't give its other stations
        frappe.set_user(WAITER)
        names = [s["name"] for s in kitchen_api.get_stations()]
        self.assertIn(self.station, names)
        self.assertNotIn(elsewhere, names)
        self.assertNotIn(same_floor, names)
        self.assertRaises(frappe.PermissionError, kitchen_api.get_station_queue, elsewhere)
        self.assertRaises(frappe.PermissionError, kitchen_api.advance, elsewhere, "x")

        # a user of the profile with no permissions sees none
        frappe.set_user(CASHIER2)
        self.assertEqual(kitchen_api.get_stations(), [])
        self.assertRaises(frappe.PermissionError, kitchen_api.get_station_queue, self.station)

        # managers see every center, and so does a role with "Every production center"
        frappe.set_user(MANAGER)
        names = [s["name"] for s in kitchen_api.get_stations()]
        self.assertIn(elsewhere, names)
        frappe.set_user("Administrator")
        frappe.db.set_value("Ren Role", "Server", "all_stations", 1)
        frappe.clear_document_cache("Ren Role", "Server")
        try:
            frappe.set_user(WAITER)
            self.assertIn(same_floor, [s["name"] for s in kitchen_api.get_stations()])
        finally:
            frappe.set_user("Administrator")
            frappe.db.set_value("Ren Role", "Server", "all_stations", 0)
            frappe.clear_document_cache("Ren Role", "Server")


class TestRecallAndVoids(KitchenCase):
    def test_recall_undo(self):
        self.new_order((("u-1" + R), ITEM_A))
        frappe.set_user(WAITER)
        kitchen_api.advance(self.station, ("u-1" + R))
        kitchen_api.advance(self.station, ("u-1" + R))
        recent = [r for r in kitchen_api.get_recent(self.station) if r["identifier"] == ("u-1" + R)]
        self.assertEqual([(r["to_status"], r["can_undo"]) for r in recent],
                         [("Completed", True), ("Processing", False)])

        kitchen_api.undo(self.station, recent[0]["name"])
        self.assertEqual(self.status(("u-1" + R)), "Processing")
        self.assertRaises(kitchen_api.KitchenConflict, kitchen_api.undo, self.station, recent[0]["name"])
        # now the earlier move is the latest one
        recent = [r for r in kitchen_api.get_recent(self.station) if r["identifier"] == ("u-1" + R)]
        self.assertEqual([(r["to_status"], r["can_undo"]) for r in recent], [("Processing", True)])

    def test_undo_only_from_the_same_center(self):
        frappe.set_user("Administrator")
        other = make_station(self.fx["floor"], "_REN Expo")
        self.new_order((("u-2" + R), ITEM_A))
        frappe.set_user(WAITER)
        kitchen_api.advance(self.station, ("u-2" + R))
        log = frappe.get_all("Ren Kitchen Status Log", filters={"identifier": ("u-2" + R)}, pluck="name")[0]
        self.assertRaises(frappe.PermissionError, kitchen_api.undo, other, log)

    def test_voided_line_shows_at_its_center(self):
        voids_api.install_default_reasons()
        order = self.new_order((("vd-1" + R), ITEM_A), (("vd-2" + R), ITEM_B))
        frappe.set_user(MANAGER)
        order_api.delete_item(order, ("vd-1" + R), reason="Kitchen error")
        frappe.set_user(WAITER)
        q = kitchen_api.get_station_queue(self.station)
        (ticket,) = ticket_of(q, order)
        self.assertEqual([i["identifier"] for i in ticket["items"]], [("vd-2" + R)])
        voided = [v for v in q["voids"] if v["order_name"] == order]
        self.assertEqual([(v["item_name"], v["reason"]) for v in voided], [(ITEM_A, "Kitchen error")])


class TestStationFlow(FrappeTestCase):
    def test_linear_flow(self):
        from renpos.patches.v2_0.station_linear_flow import legacy_flow
        rows = [frappe._dict(status_managed="Pending", next_status="Delivered"),
                frappe._dict(status_managed="Attending", next_status="Pending")]
        self.assertEqual(legacy_flow(rows), ["Attending", "Pending", "Delivered"])

        st = frappe.new_doc("Ren Station")
        st.set("status_flow", [{"status": s} for s in ("Sent", "Processing", "Completed")])
        self.assertEqual(st.working_statuses, ["Sent", "Processing"])
        self.assertEqual(st.next_status("Sent"), "Processing")
        self.assertEqual(st.next_status("Processing"), "Completed")
        self.assertRaises(frappe.ValidationError, st.next_status, "Completed")
        st.validate()

        st.set("status_flow", [{"status": "Sent"}, {"status": "Sent"}])
        self.assertRaises(frappe.ValidationError, st.validate)
        st.set("status_flow", [{"status": "Sent"}])
        self.assertRaises(frappe.ValidationError, st.validate)
        # statuses of unsent lines would hand items back to the waiter as editable
        st.set("status_flow", [{"status": s} for s in ("Sent", "Attending", "Delivered")])
        self.assertRaises(frappe.ValidationError, st.validate)


class TestEditableStatuses(FrappeTestCase):
    @staticmethod
    def clear():
        cache = getattr(frappe.local, "request_cache", None)
        if cache is not None:
            cache.clear()

    def test_editable_comes_from_the_status(self):
        from renpos.api import statuses
        self.clear()
        self.assertTrue(statuses.is_editable("Pending"))
        self.assertTrue(statuses.is_editable(None))
        self.assertFalse(statuses.is_editable("Sent"))

        st = frappe.new_doc("Ren Station")
        st.set("status_flow", [{"status": s} for s in ("Sent", "Processing", "Completed")])
        st.validate()
        # a restaurant marks Processing as editable: production flows can't use it any more
        frappe.db.set_value("Ren Order Status", "Processing", "allows_to_edit_item", 1)
        self.clear()
        try:
            self.assertTrue(statuses.is_editable("Processing"))
            self.assertRaises(frappe.ValidationError, st.validate)
        finally:
            frappe.db.set_value("Ren Order Status", "Processing", "allows_to_edit_item", 0)
            self.clear()

        sent = frappe.get_doc("Ren Order Status", "Sent")
        sent.allows_to_edit_item = 1
        self.assertRaises(frappe.ValidationError, sent.save)
        pending = frappe.get_doc("Ren Order Status", "Pending")
        pending.allows_to_edit_item = 0
        self.assertRaises(frappe.ValidationError, pending.save)


class TestStationRoomsTables(KitchenCase):
    """A station limited to some rooms and / or tables only gets their orders (kitchen display and tickets)."""

    def setUp(self):
        frappe.set_user("Administrator")
        other = frappe.db.get_value("Ren Table", {"room": self.fx["room"], "description": "_REN Other"})
        if not other:
            other = frappe.get_doc({"doctype": "Ren Table", "room": self.fx["room"], "description": "_REN Other",
                                    "no_of_seats": 2}).insert(ignore_permissions=True).name
        self.other = other
        terrace = frappe.db.get_value("Ren Room", {"floor": self.fx["floor"], "description": "_REN Terrace"})
        if not terrace:
            terrace = frappe.get_doc({"doctype": "Ren Room", "floor": self.fx["floor"],
                                      "description": "_REN Terrace"}).insert(ignore_permissions=True).name
        self.terrace = terrace

    def tearDown(self):
        frappe.set_user("Administrator")
        self.limit()

    def limit(self, rooms=None, tables=None):
        st = frappe.get_doc("Ren Station", self.station)
        st.restricted_to_rooms = 1 if rooms is not None else 0
        st.set("restricted_rooms", [{"room": r} for r in rooms or []])
        st.restricted_to_tables = 1 if tables is not None else 0
        st.set("restricted_tables", [{"table": t} for t in tables or []])
        st.save(ignore_permissions=True)

    def on_screen(self, order):
        return bool(ticket_of(kitchen_api.get_station_queue(self.station), order))

    def test_only_its_rooms_and_tables(self):
        order = self.new_order(("o-a" + R, ITEM_A))      # table T-1, in the test room
        self.assertTrue(self.on_screen(order))

        self.limit(rooms=[self.terrace])                 # the terrace only: not this order
        self.assertFalse(self.on_screen(order))
        st = frappe.get_doc("Ren Station", self.station)
        self.assertFalse(st.takes_order_from(self.fx["room"], self.fx["table"]))

        self.limit(rooms=[self.terrace], tables=[self.fx["table"]])  # ... or table T-1: yes
        self.assertTrue(self.on_screen(order))

        self.limit(tables=[self.other])                  # another table only: no
        self.assertFalse(self.on_screen(order))

        self.limit(rooms=[self.fx["room"]])              # its room: yes
        self.assertTrue(self.on_screen(order))
        self.assertEqual(frappe.get_doc("Ren Station", self.station).restricted_rooms[0].room_description, "Test room")


class TestDispatch(KitchenCase):
    """A dispatch station waits for the whole order and asks who delivers it (api/dispatch.py)."""

    def test_whole_order_and_driver(self):
        soda = "_REN-SODA-NOBODY"
        ensure_grouped_item(soda, ensure_group("_REN Nobody Makes"))
        frappe.set_user("Administrator")
        name = "_REN Dispatch"
        if frappe.db.exists("Ren Station", {"description": name}):
            frappe.delete_doc("Ren Station", frappe.db.get_value("Ren Station", {"description": name}), force=True)
        st = frappe.get_doc({
            "doctype": "Ren Station", "description": name, "floor": self.fx["floor"],
            "group_items_by_order": 1, "whole_order": 1,
            "production_center_group": [{"item_group": "Products"}, {"item_group": "_REN Nobody Makes"}],
            "status_flow": [{"status": s} for s in ("Completed", "On the way", "Delivered")],
            "restricted_to_tables": 1, "restricted_tables": [{"table": self.fx["table"]}],
        }).insert(ignore_permissions=True).name

        a, b = "d-a" + R, "d-b" + R
        order = self.new_order((a, ITEM_A), (b, soda))
        frappe.set_user("Administrator")

        # tracking: shown at once, but the kitchen still works on the steak
        (t,) = ticket_of(kitchen_api.get_station_queue(st), order)
        self.assertEqual((t["ready"], t["waiting_items"], t["total_items"], t["next_status"]), (False, 1, 2, None))
        self.assertTrue(next(i for i in t["items"] if i["identifier"] == a)["waiting"])
        self.assertRaises(frappe.ValidationError, kitchen_api.advance, st, ticket=t["key"])

        kitchen_api.advance(self.station, a)
        kitchen_api.advance(self.station, a)  # Completed
        (t,) = ticket_of(kitchen_api.get_station_queue(st), order)
        self.assertEqual((t["ready"], t["status"], t["next_status"], t["ask_driver"]), (True, "Completed", "On the way", 1))

        # the driver is required, then both lines go (the soda nobody prepares too)
        self.assertRaises(frappe.ValidationError, kitchen_api.advance, st, ticket=t["key"], expected="Completed")
        kitchen_api.advance(st, ticket=t["key"], expected="Completed", driver_name="Luis")
        self.assertEqual((self.status(a), self.status(b)), ("On the way", "On the way"))
        o = frappe.db.get_value("Ren Order", order, ["ren_driver_name", "ren_dispatched_at", "ren_delivered_at"], as_dict=True)
        self.assertEqual(o.ren_driver_name, "Luis")
        self.assertTrue(o.ren_dispatched_at and not o.ren_delivered_at)

        (t,) = ticket_of(kitchen_api.get_station_queue(st), order)
        self.assertEqual(t["driver"], "Luis")
        kitchen_api.advance(st, ticket=t["key"], expected="On the way")
        self.assertTrue(frappe.db.get_value("Ren Order", order, "ren_delivered_at"))
        self.assertFalse(ticket_of(kitchen_api.get_station_queue(st), order))
