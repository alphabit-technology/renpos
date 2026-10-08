"""Ren Booking: fill starts_at / ends_at (full datetimes) for existing reservations."""

import frappe
from frappe.utils import cint, get_datetime, get_time, getdate
from datetime import datetime, timedelta


def execute():
	frappe.reload_doc("ren_pos", "doctype", "ren_booking")
	for b in frappe.get_all("Ren Booking", filters={"starts_at": ["is", "not set"]},
	                        fields=["name", "reservation_date", "reservation_time", "duration", "status", "seated_time"]):
		if not b.reservation_date or not b.reservation_time:
			continue
		if b.status in ("Seated", "Completed") and b.seated_time:
			start = get_datetime(b.seated_time)
		else:
			start = datetime.combine(getdate(b.reservation_date), get_time(b.reservation_time))
		end = start + timedelta(minutes=cint(b.duration) or 90)
		frappe.db.set_value("Ren Booking", b.name, {"starts_at": start, "ends_at": end},
		                    update_modified=False)
