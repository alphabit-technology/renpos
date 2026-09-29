# -*- coding: utf-8 -*-
# Copyright (c) 2022, Quantum Bit Core and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.model.document import Document
from datetime import timedelta, datetime
from frappe.utils import (
    cint, get_datetime, today, now_datetime,
    getdate, get_time
)


class RestaurantBooking(Document):
    # ──────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────

    def validate(self):
        self.set_guest_display_name()
        self.compute_end_time()
        self.validate_dates()
        self.validate_party_size()
        self.set_auto_status()
        self.validate_table_availability()

    def on_update(self):
        self.sync_table_state()
        self.sync_customer_contact()
        self.track_table_change()
        self.publish_realtime()

    def onload(self):
        """Auto-expire to No Show if past end time + grace."""
        if not self.is_new() and self.status in ("Open", "Confirmed"):
            if self.is_past_end_time():
                self.db_set("status", "No Show")
                self.reload()

    # ──────────────────────────────────────────────
    # Computed Fields
    # ──────────────────────────────────────────────

    def set_guest_display_name(self):
        """Ensure we always have a display name."""
        if not self.customer_name and self.customer:
            self.customer_name = frappe.db.get_value(
                "Customer", self.customer, "customer_name"
            )
        if not self.customer_name and not self.guest_name:
            frappe.throw(_("Please provide a Customer or Guest Name"))

    def compute_end_time(self):
        """Compute reservation_end_time from time + duration."""
        if not self.reservation_time:
            return
        duration = cint(self.duration) or 120
        start = self.get_start_datetime()
        end = start + timedelta(minutes=duration)
        self.reservation_end_time = end.time().strftime("%H:%M:%S")

    def get_start_datetime(self):
        """Combine reservation_date + reservation_time into datetime."""
        return datetime.combine(
            getdate(self.reservation_date or today()),
            get_time(self.reservation_time),
        )

    def get_end_datetime(self):
        """Combine reservation_date + reservation_end_time into datetime."""
        return datetime.combine(
            getdate(self.reservation_date or today()),
            get_time(self.reservation_end_time),
        )

    # ──────────────────────────────────────────────
    # Validations
    # ──────────────────────────────────────────────

    def validate_dates(self):
        """Ensure reservation is not in the past (with 15-min grace)."""
        if self.status in ("Cancelled", "No Show", "Completed"):
            return

        start = self.get_start_datetime()
        grace = now_datetime() - timedelta(minutes=15)

        if start < grace:
            frappe.throw(
                _("Reservation time {0} is in the past").format(
                    start.strftime("%Y-%m-%d %H:%M")
                )
            )

    def validate_party_size(self):
        """Ensure party size is valid, warn if exceeds table capacity."""
        if cint(self.party_size) < 1:
            frappe.throw(_("Party size must be at least 1"))

        if not self.table:
            return

        capacity = cint(
            frappe.db.get_value("Ren Table", self.table, "no_of_seats")
        )
        if capacity and cint(self.party_size) > capacity:
            frappe.msgprint(
                _("Party of {0} exceeds table capacity of {1}").format(
                    self.party_size, capacity
                ),
                indicator="orange",
                alert=True,
            )

    def set_auto_status(self):
        """Auto-set status based on table assignment and date."""
        # Don't override terminal or manual statuses
        if self.status in ("Cancelled", "No Show", "Completed", "Seated"):
            return

        today_date = getdate(today())
        res_date = getdate(self.reservation_date)

        if self.table:
            if self.status != "Waitlisted":
                self.status = "Confirmed"
        else:
            if res_date >= today_date and self.status != "Waitlisted":
                self.status = "Open"

    def validate_table_availability(self):
        """Check for overlapping reservations on the same table."""
        if not self.table or self.status in ("Cancelled", "No Show"):
            return

        from restaurant_management.api.booking import get_table_conflicts

        conflicts = get_table_conflicts(
            table=self.table,
            date=self.reservation_date,
            time_start=self.reservation_time,
            time_end=self.reservation_end_time,
            exclude=self.name if not self.is_new() else None,
        )

        if conflicts:
            c = conflicts[0]
            frappe.throw(
                _("Table {0} is occupied from {1} to {2} by {3}").format(
                    self.table,
                    str(c.reservation_time)[:5],
                    str(c.reservation_end_time)[:5],
                    c.customer_name or c.guest_name or _("another guest"),
                )
            )

    # ──────────────────────────────────────────────
    # Side Effects
    # ──────────────────────────────────────────────

    def sync_table_state(self):
        """Notify table document to refresh its state."""
        if self.table:
            try:
                table = frappe.get_doc("Ren Table", self.table)
                if hasattr(table, "_on_update"):
                    table._on_update()
            except Exception:
                pass  # Table may not exist yet

    def sync_customer_contact(self):
        """Sync contact number to Customer record if missing."""
        if self.contact_number and self.customer:
            current = frappe.db.get_value("Customer", self.customer, "mobile_no")
            if not current:
                frappe.db.set_value(
                    "Customer", self.customer, "mobile_no", self.contact_number
                )

    def track_table_change(self):
        """If table changed, refresh old table too."""
        old = self.get_doc_before_save()
        if old and old.table and old.table != self.table:
            try:
                old_table = frappe.get_doc("Ren Table", old.table)
                if hasattr(old_table, "_on_update"):
                    old_table._on_update()
            except Exception:
                pass

    def publish_realtime(self):
        """Push update to all connected clients."""
        frappe.publish_realtime(
            "booking_update",
            {
                "name": self.name,
                "status": self.status,
                "table": self.table,
                "reservation_date": str(self.reservation_date),
            },
            after_commit=True,
        )

    # ──────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────

    def is_past_end_time(self, grace_minutes=30):
        """Check if current time is past reservation end + grace."""
        end = self.get_end_datetime()
        return now_datetime() > (end + timedelta(minutes=grace_minutes))

    # ──────────────────────────────────────────────
    # Action Methods (called from API)
    # ──────────────────────────────────────────────

    def seat(self):
        """Mark guest as seated."""
        if self.status in ("Cancelled", "No Show", "Completed"):
            frappe.throw(_("Cannot seat: booking is {0}").format(self.status))
        if not self.table:
            frappe.throw(_("Cannot seat: no table assigned"))
        self.status = "Seated"
        self.seated_time = now_datetime()
        self.save()

    def complete(self):
        """Mark reservation as completed (guest left)."""
        self.status = "Completed"
        self.completed_time = now_datetime()
        self.save()

    def cancel_booking(self, reason=None, cancelled_by=None):
        """Cancel the reservation."""
        if self.status in ("Seated", "Completed"):
            frappe.throw(
                _("Cannot cancel a {0} reservation").format(self.status)
            )
        self.status = "Cancelled"
        self.cancellation_reason = reason
        self.cancelled_by = cancelled_by or frappe.session.user
        self.save()

    def mark_no_show(self):
        """Mark as no-show."""
        self.status = "No Show"
        self.save()