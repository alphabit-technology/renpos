# -*- coding: utf-8 -*-
"""Reservations: times across midnight, late arrivals, no-shows, statuses, waitlist, pacing, floor plan."""

from datetime import timedelta

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, get_datetime, now_datetime, nowdate

from renpos.api import booking as B
from renpos.tests.test_order_flow import CUSTOMER, MANAGER, RESTAURANT, WAITER, setup_fixtures


def make_table(room, label, seats=4):
    name = frappe.db.get_value("Ren Table", {"room": room, "description": label})
    if name:
        return name
    return frappe.get_doc({"doctype": "Ren Table", "room": room, "description": label,
                           "no_of_seats": seats}).insert(ignore_permissions=True).name


def at(minutes):
    """(date, time) `minutes` from now."""
    t = now_datetime() + timedelta(minutes=minutes)
    return t.date(), t.strftime("%H:%M:%S")


class TestReservations(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.fx = setup_fixtures()
        cls.t1 = make_table(cls.fx["room"], "R-1")
        cls.t2 = make_table(cls.fx["room"], "R-2")
        cls.t3 = make_table(cls.fx["room"], "R-3", seats=8)
        if not frappe.db.exists("Ren Reservation Settings", RESTAURANT):
            frappe.get_doc({"doctype": "Ren Reservation Settings", "restaurant": RESTAURANT}).insert()
        s = frappe.get_doc("Ren Reservation Settings", RESTAURANT)
        s.update({"default_duration": 90, "no_show_after_minutes": 30, "late_grace_minutes": 15,
                  "reserved_before_minutes": 60, "slot_minutes": 15, "max_covers_per_slot": 0,
                  "max_party_size": 12, "opening_hours": []})
        s.set("turn_times", [{"min_party": 5, "max_party": 8, "minutes": 150}])
        s.save()
        # nothing left from earlier runs on the test tables
        for name in frappe.get_all("Ren Booking", filters={"table": ["in", [cls.t1, cls.t2, cls.t3]]},
                                   pluck="name"):
            frappe.delete_doc("Ren Booking", name, force=True, ignore_permissions=True)
        for name in frappe.get_all("Ren Order", filters={"table": ["in", [cls.t1, cls.t2, cls.t3]]}, pluck="name"):
            frappe.delete_doc("Ren Order", name, force=True, ignore_permissions=True)

    def tearDown(self):
        frappe.set_user("Administrator")
        for name in frappe.get_all("Ren Booking", filters={"guest_name": ["in", ["No table", "No table 2",
                                                                                       "Test Guest", "Second"]]},
                                   pluck="name"):
            frappe.delete_doc("Ren Booking", name, force=True, ignore_permissions=True)
        for name in frappe.get_all("Ren Booking", filters={"table": ["in", [self.t1, self.t2, self.t3]]},
                                   pluck="name"):
            frappe.delete_doc("Ren Booking", name, force=True, ignore_permissions=True)
        for name in frappe.get_all("Ren Order", filters={"table": ["in", [self.t1, self.t2, self.t3]]},
                                   pluck="name"):
            frappe.delete_doc("Ren Order", name, force=True, ignore_permissions=True)

    def book(self, minutes=60, table=None, party=2, date=None, time=None, **kw):
        d, t = at(minutes)
        return B.create_reservation(guest_name=kw.pop("guest", "Test Guest"), party_size=party,
                                    reservation_date=date or d, reservation_time=time or t,
                                    table=table, **kw)

    def backdate(self, name, minutes):
        """Pretend the reservation was for `minutes` ago (creating it in the past isn't allowed)."""
        start = now_datetime() - timedelta(minutes=minutes)
        dur = frappe.db.get_value("Ren Booking", name, "duration")
        frappe.db.set_value("Ren Booking", name, {
            "reservation_date": start.date(), "reservation_time": start.strftime("%H:%M:%S"),
            "starts_at": start, "ends_at": start + timedelta(minutes=dur)})

    # ── times ──

    def test_party_size_sets_table_time_and_datetimes(self):
        frappe.set_user(WAITER)
        b = self.book(120, self.t3, party=6)
        self.assertEqual(b["duration"], 150)
        self.assertEqual(get_datetime(b["ends_at"]) - get_datetime(b["starts_at"]), timedelta(minutes=150))
        self.assertEqual(b["status"], "Confirmed")
        doc = frappe.get_doc("Ren Booking", b["name"])
        self.assertEqual(doc.restaurant, RESTAURANT)
        self.assertEqual(doc.room, self.fx["room"])

    def test_reservation_across_midnight_holds_the_table(self):
        frappe.set_user(WAITER)
        day = add_days(nowdate(), 2)
        late = B.create_reservation(guest_name="Late dinner", party_size=2, reservation_date=day,
                                    reservation_time="23:30", table=self.t1)
        self.assertEqual(get_datetime(late["ends_at"]).date(), get_datetime(add_days(day, 1)).date())
        # 00:30 next day on the same table overlaps the 23:30 + 90 min party
        self.assertRaises(frappe.ValidationError, B.create_reservation, guest_name="After", party_size=2,
                          reservation_date=add_days(day, 1), reservation_time="00:30", table=self.t1)
        avail = {t["name"]: t for t in B.get_table_availability(add_days(day, 1), "00:30", party_size=2)}
        self.assertFalse(avail[self.t1]["available"])
        self.assertTrue(avail[self.t2]["available"])

    def test_new_reservation_cannot_be_in_the_past(self):
        frappe.set_user(WAITER)
        self.assertRaises(frappe.ValidationError, self.book, -60, self.t1)

    # ── arrival ──

    def test_late_party_can_be_seated_and_gets_an_order(self):
        frappe.set_user(WAITER)
        b = self.book(30, self.t1, party=3, notes="Birthday")
        self.backdate(b["name"], 25)  # 25 min late: past the 15 min grace
        res = B.check_in_reservation(b["name"])
        self.assertEqual(res["status"], "Seated")
        order = frappe.get_doc("Ren Order", res["order"])
        self.assertEqual((order.table, order.dinners), (self.t1, 3))
        self.assertIn("Birthday", order.notes)
        self.assertEqual(res["table_order"], order.name)
        # the table is held from the seating, not the old reservation time
        self.assertLess(abs((get_datetime(res["starts_at"]) - now_datetime()).total_seconds()), 120)
        # still editable once seated
        B.update_reservation(b["name"], internal_notes="Window")

    def test_seat_on_another_table(self):
        frappe.set_user(WAITER)
        b = self.book(10, None)
        self.assertEqual(b["status"], "Open")
        res = B.check_in_reservation(b["name"], table=self.t2)
        self.assertEqual((res["status"], res["table"]), ("Seated", self.t2))
        # a table with an open order can't take another party
        c = self.book(15, None, guest="Second")
        self.assertRaises(frappe.ValidationError, B.check_in_reservation, c["name"], table=self.t2)

    def test_no_show_job(self):
        frappe.set_user(WAITER)
        late = self.book(30, self.t1, guest="Gone")
        soon = self.book(30, self.t2, guest="Coming")
        self.backdate(late["name"], 45)   # 45 min after: No Show (30)
        self.backdate(soon["name"], 10)   # 10 min after: still waiting
        frappe.set_user("Administrator")
        B.auto_expire_no_shows()
        self.assertEqual(frappe.db.get_value("Ren Booking", late["name"], "status"), "No Show")
        self.assertEqual(frappe.db.get_value("Ren Booking", soon["name"], "status"), "Confirmed")
        # the guest shows up after all
        frappe.set_user(WAITER)
        self.assertEqual(B.check_in_reservation(late["name"])["status"], "Seated")

    def test_late_reservation_can_be_edited_and_reinstated_no_show_stays(self):
        frappe.set_user(WAITER)
        b = self.book(30, self.t1)
        self.backdate(b["name"], 40)
        # the form sends "HH:MM": not a time change, so no "in the past" error
        t = frappe.db.get_value("Ren Booking", b["name"], "reservation_time")
        B.update_reservation(b["name"], contact_number="555-0100", reservation_time=frappe.utils.get_time(t).strftime("%H:%M"))
        frappe.set_user("Administrator")
        B.auto_expire_no_shows()
        self.assertEqual(frappe.db.get_value("Ren Booking", b["name"], "status"), "No Show")
        frappe.set_user(WAITER)
        B.set_status(b["name"], "Confirmed")  # the guest called: on the way
        frappe.set_user("Administrator")
        B.auto_expire_no_shows()
        self.assertEqual(frappe.db.get_value("Ren Booking", b["name"], "status"), "Confirmed")
        self.assertRaises(frappe.ValidationError, B.set_status, b["name"], "Seated")

    def test_no_show_job_near_midnight_spares_later_reservations(self):
        # the old job compared times only: at 00:10 every reservation ending before 23:40 became No Show
        frappe.set_user(WAITER)
        later = self.book(240, self.t1)
        frappe.set_user("Administrator")
        B.auto_expire_no_shows()
        self.assertEqual(frappe.db.get_value("Ren Booking", later["name"], "status"), "Confirmed")

    # ── statuses ──

    def test_status_rules(self):
        frappe.set_user(WAITER)
        b = self.book(60, self.t1)
        B.cancel_reservation(b["name"], reason="Called")
        self.assertEqual(B.set_status(b["name"], "Confirmed")["status"], "Confirmed")  # reinstated
        B.check_in_reservation(b["name"], create_order=0)
        B.complete_reservation(b["name"])
        self.assertRaises(frappe.ValidationError, B.set_status, b["name"], "Confirmed")
        self.assertRaises(frappe.ValidationError, B.cancel_reservation, b["name"])

    def test_paying_completes_the_reservation(self):
        frappe.set_user(WAITER)
        b = self.book(5, self.t1)
        order = B.check_in_reservation(b["name"])["order"]
        doc = frappe.get_doc("Ren Order", order)
        doc.status = "Invoiced"
        B.on_table_order_update(doc, "on_update")
        self.assertEqual(frappe.db.get_value("Ren Booking", b["name"], "status"), "Completed")

    # ── waitlist ──

    def test_waitlist_does_not_hold_tables(self):
        frappe.set_user(WAITER)
        w = B.add_to_waitlist(guest_name="Walk in", party_size=2, quoted_wait=20)
        self.assertEqual(w["status"], "Waitlisted")
        day = B.get_day()
        self.assertTrue(any(x["name"] == w["name"] for x in day["bookings"]))
        avail = {t["name"]: t for t in B.get_table_availability(*at(5), party_size=2)}
        self.assertTrue(avail[self.t1]["available"])
        res = B.check_in_reservation(w["name"], table=self.t1)
        self.assertEqual(res["status"], "Seated")
        self.assertTrue(res["order"])

    # ── pacing & slots ──

    def test_pacing_limits_guests_per_slot(self):
        frappe.set_user("Administrator")
        frappe.db.set_value("Ren Reservation Settings", RESTAURANT, "max_covers_per_slot", 4)
        frappe.clear_document_cache("Ren Reservation Settings", RESTAURANT)
        try:
            frappe.set_user(WAITER)
            day = add_days(nowdate(), 3)
            B.create_reservation(guest_name="A", party_size=2, reservation_date=day, reservation_time="19:00",
                                 table=self.t1)
            B.create_reservation(guest_name="B", party_size=2, reservation_date=day, reservation_time="19:05",
                                 table=self.t2)
            # guests without a table count for pacing too
            B.create_reservation(guest_name="No table", party_size=2, reservation_date=day, reservation_time="19:30")
            B.create_reservation(guest_name="No table 2", party_size=2, reservation_date=day, reservation_time="19:35")
            slots = {s["time"]: s for s in B.get_slots(day, 2)["slots"]}
            self.assertFalse(slots["19:30"]["available"])
            self.assertFalse(slots["19:00"]["available"])
            self.assertTrue(slots["19:15"]["available"])
            self.assertRaises(frappe.ValidationError, B.create_reservation, guest_name="C", party_size=2,
                              reservation_date=day, reservation_time="19:10", table=self.t3)
            # a manager can squeeze a party in
            frappe.set_user(MANAGER)
            B.create_reservation(guest_name="VIP", party_size=2, reservation_date=day, reservation_time="19:10",
                                 table=self.t3)
        finally:
            frappe.set_user("Administrator")
            frappe.db.set_value("Ren Reservation Settings", RESTAURANT, "max_covers_per_slot", 0)
            frappe.clear_document_cache("Ren Reservation Settings", RESTAURANT)

    def test_slots_respect_hours_and_tables(self):
        frappe.set_user("Administrator")
        s = frappe.get_doc("Ren Reservation Settings", RESTAURANT)
        day = add_days(nowdate(), 4)
        weekday = B.WEEKDAYS[get_datetime(day).weekday()]
        s.set("opening_hours", [{"weekday": weekday, "opens": "18:00", "closes": "21:00"}])
        s.save()
        try:
            frappe.set_user(WAITER)
            times = [x["time"] for x in B.get_slots(day, 2)["slots"]]
            self.assertEqual((times[0], times[-1]), ("18:00", "21:00"))
            self.assertRaises(frappe.ValidationError, B.create_reservation, guest_name="Early", party_size=2,
                              reservation_date=day, reservation_time="12:00", table=self.t1)
        finally:
            frappe.set_user("Administrator")
            s.reload()
            s.set("opening_hours", [])
            s.save()

    # ── floor plan ──

    def test_table_shows_reserved(self):
        frappe.set_user(WAITER)
        b = self.book(30, self.t1, guest="Ana")
        table = frappe.get_doc("Ren Table", self.t1)
        data = table.get_obj_data()
        self.assertEqual(data["status"], "Reserved")
        self.assertEqual(data["reservation"]["guest"], "Ana")
        # far away: not reserved yet
        far = self.book(240, self.t2)
        self.assertEqual(frappe.get_doc("Ren Table", self.t2).get_obj_data()["status"], "Available")
        B.cancel_reservation(b["name"])
        self.assertEqual(frappe.get_doc("Ren Table", self.t1).get_obj_data()["status"], "Available")
        self.assertTrue(far)

    def test_guest_history(self):
        frappe.set_user(WAITER)
        b = B.create_reservation(customer=CUSTOMER, party_size=2, reservation_date=at(60)[0],
                                 reservation_time=at(60)[1], table=self.t1)
        B.mark_no_show(b["name"])
        day = B.get_day(at(60)[0])
        mine = [x for x in day["bookings"] if x["name"] == b["name"]][0]
        self.assertGreaterEqual(mine["guest"]["no_shows"], 1)


class TestOnlineBooking(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.fx = setup_fixtures()
        cls.small = make_table(cls.fx["room"], "O-2", seats=2)
        cls.big = make_table(cls.fx["room"], "O-6", seats=6)

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.set_value("Ren Reservation Settings", RESTAURANT, "online_enabled", 0)
        frappe.clear_document_cache("Ren Reservation Settings", RESTAURANT)

    def test_guest_books_online(self):
        from renpos.api import public_booking as P
        frappe.set_user("Guest")
        day = add_days(nowdate(), 5)
        self.assertRaises(frappe.ValidationError, P.get_times, RESTAURANT, day, 2)  # not enabled yet
        frappe.set_user("Administrator")
        frappe.db.set_value("Ren Reservation Settings", RESTAURANT, {"online_enabled": 1, "online_max_party": 6})
        frappe.clear_document_cache("Ren Reservation Settings", RESTAURANT)
        frappe.set_user("Guest")
        times = P.get_times(RESTAURANT, day, 2)
        self.assertIn("20:00", times)
        self.assertRaises(frappe.ValidationError, P.get_times, RESTAURANT, day, 9)  # too big for online
        res = P.book(RESTAURANT, day, "20:00", 2, "Online Guest", "+1 617 555 0101", "guest@example.com",
                     notes="<b>window</b>")
        frappe.set_user("Administrator")
        doc = frappe.get_doc("Ren Booking", res["reference"])
        self.assertEqual((doc.source, doc.status, doc.restaurant), ("Online", "Confirmed", RESTAURANT))
        self.assertNotIn("<b>", doc.notes)
        self.assertEqual(frappe.db.get_value("Ren Table", doc.table, "no_of_seats") >= 2, True)
        frappe.delete_doc("Ren Booking", doc.name, force=True, ignore_permissions=True)
        frappe.set_user("Guest")
        self.assertRaises(frappe.ValidationError, P.book, RESTAURANT, day, "20:00", 2, "X", "123", "bad-email")
