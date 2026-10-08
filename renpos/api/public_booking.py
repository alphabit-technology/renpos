# -*- coding: utf-8 -*-
# renpos/api/public_booking.py
#
# Online reservations (/reserve): guests pick a date, party size and time;
# a free table that fits is assigned automatically. Only restaurants with
# "Accept Online Reservations" in their Ren Reservation Settings.
# Rate limited per IP. Guests never see other bookings or table names.

import re

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, getdate, today, add_days, escape_html

from renpos.api import booking as B


def _restaurant(restaurant):
    if not restaurant or not frappe.db.exists("Ren Reservation Settings", restaurant):
        frappe.throw(_("This restaurant doesn't take online reservations"))
    policy = B.get_policy(restaurant)
    if not cint(frappe.db.get_value("Ren Reservation Settings", restaurant, "online_enabled")) \
            or not cint(policy.enabled):
        frappe.throw(_("This restaurant doesn't take online reservations"))
    return policy


def online_restaurants():
    rows = frappe.get_all("Ren Reservation Settings", filters={"online_enabled": 1, "enabled": 1},
                          fields=["restaurant", "online_max_party", "online_note", "max_advance_days"])
    for r in rows:
        r["restaurant_name"] = frappe.db.get_value("Ren Restaurant", r.restaurant, "restaurant_name") or r.restaurant
    return rows


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=120, seconds=60 * 10)
def get_times(restaurant, date, party_size=2):
    """Bookable times only (no table or guest information)."""
    policy = _restaurant(restaurant)
    party = cint(party_size)
    max_party = cint(frappe.db.get_value("Ren Reservation Settings", restaurant, "online_max_party")) or 8
    if party < 1 or party > max_party:
        frappe.throw(_("For parties larger than {0}, please call us").format(max_party))
    day = getdate(date)
    if day < getdate(today()) or day > getdate(add_days(today(), cint(policy.max_advance_days) or 60)):
        return []
    res = B.compute_slots(day, party, restaurant)
    return [s["time"] for s in res["slots"] if s["available"]]


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=5, seconds=60 * 60)
def book(restaurant, date, time, party_size, guest_name, contact_number, email, notes=None):
    _restaurant(restaurant)
    guest_name = (guest_name or "").strip()[:140]
    contact_number = re.sub(r"[^\d+()\- ]", "", contact_number or "")[:30]
    email = (email or "").strip()[:140]
    if not guest_name or len(re.sub(r"\D", "", contact_number)) < 7:
        frappe.throw(_("Please enter your name and a phone number"))
    if not frappe.utils.validate_email_address(email):
        frappe.throw(_("Please enter a valid email"))
    party = cint(party_size)
    if time not in get_times(restaurant, date, party):
        frappe.throw(_("That time is no longer available. Please pick another one."))

    # smallest free table that fits the party
    res = B.compute_slots(getdate(date), party, restaurant, with_tables=True)
    slot = next((s for s in res["slots"] if s["time"] == time and s["available"]), None)
    if not slot:
        frappe.throw(_("That time is no longer available. Please pick another one."))
    seats = {t.name: cint(t.capacity) or 99 for t in B._restaurant_tables(restaurant)}
    table = sorted(slot["free_tables"], key=lambda n: seats.get(n, 99))[0]

    doc = frappe.get_doc({
        "doctype": "Ren Booking", "restaurant": restaurant, "source": "Online",
        "guest_name": guest_name, "contact_number": contact_number, "email": email,
        "party_size": party, "reservation_date": getdate(date), "reservation_time": time, "table": table,
        "notes": escape_html((notes or "").strip()[:500]),
    })
    doc.flags.ignore_permissions = True
    doc.insert()
    return {"reference": doc.name, "date": str(doc.reservation_date), "time": time, "party_size": party}
