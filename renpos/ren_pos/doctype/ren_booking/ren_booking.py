# Copyright (c) 2022, Quantum Bit Core and contributors
# For license information, please see license.txt
#
# Ren Booking: a reservation, a waitlist entry or a walk-in.
# Rules (table time, grace, hours, pacing, messages) come from the
# restaurant's Ren Reservation Settings; see api/booking.py.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, get_datetime, get_time, getdate, now_datetime, today
from datetime import datetime, timedelta

from renpos.api import booking as B


class RenBooking(Document):
    # ──────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────

    def validate(self):
        self.set_guest_display_name()
        self.set_location()
        self._policy = B.get_policy(self.restaurant)
        self.set_duration()
        self.compute_times()
        self.set_auto_status()
        self.validate_transition()
        self.validate_dates()
        self.validate_party_size()
        self.validate_hours_and_pacing()
        self.validate_table_availability()

    def on_update(self):
        self.sync_customer_contact()
        self.refresh_tables()
        B._publish(self)
        if self.flags.send_confirmation:
            self.send_confirmation()

    def after_insert(self):
        # sent from on_update, which runs right after
        self.flags.send_confirmation = self.status in B.UPCOMING

    # ──────────────────────────────────────────────
    # Computed fields
    # ──────────────────────────────────────────────

    def set_guest_display_name(self):
        if self.customer:
            self.customer_name = frappe.db.get_value("Customer", self.customer, "customer_name") or self.customer
        elif self.guest_name:
            self.customer_name = self.guest_name
        else:
            frappe.throw(_("Please provide a Customer or Guest Name"))

    def set_location(self):
        """Restaurant, room and floor come from the table (or the POS Profile)."""
        if self.table:
            row = frappe.db.sql(
                """SELECT r.name, r.floor, f.restaurant FROM `tabRen Table` t
                JOIN `tabRen Room` r ON r.name = t.room JOIN `tabRen Floor` f ON f.name = r.floor
                WHERE t.name = %s""", self.table, as_dict=True)
            if row:
                self.room, self.floor, self.restaurant = row[0].name, row[0].floor, row[0].restaurant or self.restaurant
        if not self.restaurant and self.pos_profile:
            self.restaurant = frappe.db.get_value("POS Profile", self.pos_profile, "ren_restaurant")
        if not self.restaurant:
            self.restaurant = B.current_restaurant()
        if self.restaurant and not self.company:
            self.company = frappe.db.get_value("Ren Restaurant", self.restaurant, "company")

    def set_duration(self):
        if not cint(self.duration):
            self.duration = B.duration_for(self._policy, self.party_size)

    def compute_times(self):
        """starts_at / ends_at: the time the tables are held. Once seated, from the seating."""
        if self.status in ("Seated", "Completed") and self.seated_time:
            start = get_datetime(self.seated_time)
        else:
            if not self.reservation_time:
                frappe.throw(_("Reservation time is required"))
            start = datetime.combine(getdate(self.reservation_date or today()), get_time(self.reservation_time))
        end = start + timedelta(minutes=cint(self.duration))
        self.starts_at, self.ends_at = start, end
        self.reservation_end_time = end.strftime("%H:%M:%S")

    # ──────────────────────────────────────────────
    # Validations
    # ──────────────────────────────────────────────

    def set_auto_status(self):
        """Open <-> Confirmed follows whether a table is assigned."""
        if not self.status:
            self.status = "Open"
        if self.status in ("Open", "Confirmed"):
            self.status = "Confirmed" if self.table else "Open"

    def validate_transition(self):
        before = self.get_doc_before_save()
        old = before.status if before else None
        if old == self.status:
            return
        allowed = set(B.TRANSITIONS.get(old, set()))
        if B.is_manager():
            allowed |= B.MANAGER_TRANSITIONS.get(old, set())
        # Open <-> Confirmed is decided by the table
        if old in ("Open", "Confirmed") and self.status in ("Open", "Confirmed"):
            return
        if self.status not in allowed:
            frappe.throw(_("A reservation can't go from {0} to {1}").format(_(old or "New"), _(self.status)))
        # a No Show the host brought back isn't expired again by the scheduled job
        if old == "No Show" and self.status in B.UPCOMING:
            self.keep_until_seated = 1

    def _time_changed(self):
        """Date or time really moved (to the minute: "19:00" from the form equals 19:00:00)."""
        before = self.get_doc_before_save()
        if self.is_new() or not before:
            return True
        def minute(t):
            return get_time(t).replace(second=0, microsecond=0) if t else None
        return (getdate(before.reservation_date) != getdate(self.reservation_date)
                or minute(before.reservation_time) != minute(self.reservation_time))

    def validate_dates(self):
        """
        New reservations (and moved ones) can't be in the past. Existing
        reservations can always be seated, edited or closed, however late.
        """
        if self.status not in B.UPCOMING or not self._time_changed():
            return
        grace = cint(self._policy.late_grace_minutes) or 15
        if get_datetime(self.starts_at) < now_datetime() - timedelta(minutes=grace):
            frappe.throw(_("Reservation time {0} is in the past").format(
                get_datetime(self.starts_at).strftime("%Y-%m-%d %H:%M")))
        days = cint(self._policy.max_advance_days)
        if days and getdate(self.starts_at) > getdate(today()) + timedelta(days=days):
            frappe.throw(_("Reservations are taken up to {0} days ahead").format(days))

    def validate_party_size(self):
        size = cint(self.party_size)
        if size < 1:
            frappe.throw(_("Party size must be at least 1"))
        limit = cint(self._policy.max_party_size)
        if limit and size > limit and not B.is_manager() and self.is_new():
            frappe.throw(_("Parties larger than {0} need a manager").format(limit))
        tables = B.booking_tables(self)
        if tables:
            seats = sum(cint(s) for s in frappe.get_all("Ren Table", filters={"name": ["in", tables]},
                                                         pluck="no_of_seats"))
            if seats and size > seats:
                frappe.msgprint(_("Party of {0} at {1} seats").format(size, seats), indicator="orange", alert=True)

    def validate_hours_and_pacing(self):
        if self.status not in B.UPCOMING or not self._time_changed():
            return
        start = get_datetime(self.starts_at)
        if not B.is_open_at(self._policy, start) and not B.is_manager():
            frappe.throw(_("{0} is outside reservation hours").format(start.strftime("%a %H:%M")))
        cap = cint(self._policy.max_covers_per_slot)
        if cap and not B.is_manager():
            step = cint(self._policy.slot_minutes) or 15
            slot_start = start - timedelta(minutes=(start.minute % step), seconds=start.second)
            covers = frappe.db.sql(
                """SELECT IFNULL(SUM(party_size), 0) FROM `tabRen Booking`
                WHERE status IN ('Open', 'Confirmed') AND starts_at >= %s AND starts_at < %s AND name != %s
                  AND IFNULL(restaurant, '') = %s""",
                (slot_start, slot_start + timedelta(minutes=step), self.name or "", self.restaurant or ""))[0][0]
            if cint(covers) + cint(self.party_size) > cap:
                frappe.throw(_("The {0} slot already has {1} of {2} guests (kitchen pacing)").format(
                    slot_start.strftime("%H:%M"), cint(covers), cap))

    def validate_table_availability(self):
        if self.status not in B.HOLDING:
            return
        tables = B.booking_tables(self)
        if tables:
            # serialize concurrent bookings of the same tables (online + host stand)
            frappe.db.sql("SELECT name FROM `tabRen Table` WHERE name IN %s FOR UPDATE", [tables])
        conflicts = B.holding_bookings(tables, self.starts_at, self.ends_at, exclude=self.name)
        if conflicts:
            c = conflicts[0]
            frappe.throw(_("Table {0} is held from {1} to {2} by {3}").format(
                frappe.db.get_value("Ren Table", c.table, "description") or c.table,
                get_datetime(c.starts_at).strftime("%H:%M"), get_datetime(c.ends_at).strftime("%H:%M"),
                B._guest(c)))

    # ──────────────────────────────────────────────
    # Side effects
    # ──────────────────────────────────────────────

    def refresh_tables(self):
        """Floor plans redraw the tables this booking holds (and the ones it left)."""
        tables = set(B.booking_tables(self))
        before = self.get_doc_before_save()
        if before:
            tables |= set(B.booking_tables(before))
        for t in tables:
            if frappe.db.exists("Ren Table", t):
                frappe.get_doc("Ren Table", t).on_change()

    def sync_customer_contact(self):
        if self.contact_number and self.customer:
            if not frappe.db.get_value("Customer", self.customer, "mobile_no"):
                frappe.db.set_value("Customer", self.customer, "mobile_no", self.contact_number)

    def send_confirmation(self):
        self.flags.send_confirmation = False
        if cint(self.confirmation_sent) or not cint(self._policy.get("send_confirmation")):
            return
        try:
            if B.send_guest_message(self, "confirmation", self._policy):
                self.db_set("confirmation_sent", 1)
        except Exception:
            frappe.log_error(title="Restaurant: reservation confirmation not sent", reference_doctype=self.doctype,
                             reference_name=self.name)

    # ──────────────────────────────────────────────
    # Actions
    # ──────────────────────────────────────────────

    def seat(self, table=None, create_order=True):
        """Seat the party now (early, on time or late), on its table or another one."""
        if "Seated" not in B.TRANSITIONS.get(self.status, set()):
            frappe.throw(_("Cannot seat: the reservation is {0}").format(_(self.status)))
        if table:
            self.table = table
        if not self.table:
            frappe.throw(_("Choose a table to seat the party"))
        busy = B.tables_with_open_orders(B.booking_tables(self), exclude_order=self.table_order)
        if busy:
            frappe.throw(_("Table {0} still has an open order").format(
                ", ".join(frappe.db.get_value("Ren Table", t, "description") or t for t in busy)))
        self.status = "Seated"
        self.seated_time = now_datetime()
        self.save()
        order = None
        if create_order:
            order = self.open_order()
        return order

    def open_order(self):
        from renpos.api import order as order_api
        res = order_api.add_order(self.table)
        name = res["order"]["data"]["name"]
        updates = {"dinners": cint(self.party_size)}
        if self.customer:
            updates["customer"] = self.customer
            updates["customer_name"] = self.customer_name
        note = " · ".join(x for x in (_("Reservation {0}").format(self.name), self.notes) if x)
        updates["notes"] = note
        frappe.db.set_value("Ren Order", name, updates)
        self.db_set("table_order", name)
        if self.customer:
            frappe.db.set_value("Ren Table", self.table, "customer", self.customer)
        frappe.get_doc("Ren Table", self.table).on_change()
        return name

    def complete(self):
        self.status = "Completed"
        self.completed_time = now_datetime()
        self.save()

    def cancel_booking(self, reason=None, cancelled_by=None):
        self.status = "Cancelled"
        self.cancellation_reason = reason
        self.cancelled_by = cancelled_by or frappe.session.user
        self.save()

    def mark_no_show(self):
        self.status = "No Show"
        self.save()
