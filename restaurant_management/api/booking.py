# -*- coding: utf-8 -*-
# ren_restaurant/api/booking.py
#
# Whitelisted API methods for the Reservation React form.
# All methods called via: frappe.call({ method: "restaurant_management.restaurant_management.api.booking.<fn>" })

from __future__ import unicode_literals
import frappe
from restaurant_management.api.guards import require_restaurant_user
from frappe import _
from frappe.utils import cint, today, now_datetime, getdate, get_time
from datetime import timedelta, datetime


# ══════════════════════════════════════════════════
# TABLE AVAILABILITY
# ══════════════════════════════════════════════════

@frappe.whitelist()
def get_table_availability(date, time_start, time_end, party_size=0):
    """
    Returns all tables for a restaurant with availability status
    for the requested time range.

    Used by the React form's table selection grid.

    Returns list of dicts:
        {
            name, table_name, capacity, room, room_name,
            available (bool), status_indicator (green|red|gray),
            conflict_info (str), reservations_today (list)
        }
    """
    require_restaurant_user()
    party_size = cint(party_size)
    date = getdate(date)

    # All tables in this restaurant
    # Tables of the user's restaurant (all tables if it can't be resolved)
    from restaurant_management.api.guards import current_pos_profile
    profile = current_pos_profile()
    restaurant = frappe.db.get_value("POS Profile", profile, "ren_restaurant") if profile else None
    tables = frappe.db.sql(
        """
        SELECT t.name, t.description AS table_name, t.no_of_seats AS capacity,
               t.room, r.description AS room_name
        FROM `tabRen Table` t
        LEFT JOIN `tabRen Room` r ON r.name = t.room
        LEFT JOIN `tabRen Floor` f ON f.name = r.floor
        WHERE (%(restaurant)s IS NULL OR f.restaurant = %(restaurant)s)
        ORDER BY t.description ASC
        """,
        {"restaurant": restaurant},
        as_dict=True,
    )
    for t in tables:
        t["room_name"] = t.room_name or t.room or ""

    # All active reservations for this date — single query
    active = frappe.db.sql(
        """
        SELECT
            name, `table`, reservation_time, reservation_end_time,
            customer_name, guest_name, party_size, status
        FROM `tabRestaurant Booking`
        WHERE reservation_date = %(date)s
          AND status IN ('Open', 'Confirmed', 'Waitlisted', 'Seated')
        """,
        {"date": date},
        as_dict=True,
    )

    # Index by table
    by_table = {}
    for r in active:
        by_table.setdefault(r["table"], []).append(r)

    req_start = get_time(time_start)
    req_end = get_time(time_end)

    result = []
    for t in tables:
        table_bookings = by_table.get(t.name, [])

        # Find time conflicts
        conflicts = []
        for r in table_bookings:
            r_start = get_time(r.reservation_time)
            r_end = get_time(r.reservation_end_time)
            # Overlap: r_start < req_end AND r_end > req_start
            if r_start < req_end and r_end > req_start:
                conflicts.append(r)

        has_capacity = (not party_size) or (cint(t.capacity) >= party_size)

        if conflicts:
            c = conflicts[0]
            t["available"] = False
            t["status_indicator"] = "red"
            t["conflict_info"] = "{guest} ({pax})  {start}-{end}".format(
                guest=c.customer_name or c.guest_name or _("Reserved"),
                pax=c.party_size,
                start=str(c.reservation_time)[:5],
                end=str(c.reservation_end_time)[:5],
            )
        elif not has_capacity:
            t["available"] = False
            t["status_indicator"] = "gray"
            t["conflict_info"] = _("Capacity {0}, need {1}").format(
                t.capacity, party_size
            )
        else:
            t["available"] = True
            t["status_indicator"] = "green"
            t["conflict_info"] = ""

        t["reservations_today"] = table_bookings
        result.append(t)

    return result


# ══════════════════════════════════════════════════
# CREATE
# ══════════════════════════════════════════════════

@frappe.whitelist()
def create_reservation(**kwargs):
    """
    Create a new Restaurant Booking.
    Called from the React form's "Create Reservation" button.

    Required args: restaurant, party_size, reservation_date, reservation_time
    Optional: customer, customer_name, guest_name, contact_number, email,
              duration, table, notes, source, pos_profile
    """
    require_restaurant_user()
    # Require at least a guest identifier
    if not kwargs.get("customer") and not kwargs.get("guest_name"):
        frappe.throw(_("Please provide a Customer or Guest Name"))

    if not kwargs.get("reservation_date"):
        frappe.throw(_("Reservation date is required"))

    if not kwargs.get("reservation_time"):
        frappe.throw(_("Reservation time is required"))

    doc = frappe.get_doc(
        {
            "doctype": "Restaurant Booking",
            "company": kwargs.get("company") or frappe.defaults.get_user_default("company"),
            "pos_profile": kwargs.get("pos_profile"),
            "customer": kwargs.get("customer"),
            "customer_name": kwargs.get("customer_name"),
            "guest_name": kwargs.get("guest_name"),
            "contact_number": kwargs.get("contact_number"),
            "email": kwargs.get("email"),
            "party_size": cint(kwargs.get("party_size")) or 2,
            "reservation_date": kwargs.get("reservation_date"),
            "reservation_time": kwargs.get("reservation_time"),
            "duration": cint(kwargs.get("duration")) or 120,
            "table": kwargs.get("table"),
            "notes": kwargs.get("notes"),
            "source": kwargs.get("source") or "Phone",
        }
    )

    doc.insert()

    return {
        "name": doc.name,
        "status": doc.status,
        "table": doc.table,
        "reservation_date": str(doc.reservation_date),
        "reservation_time": str(doc.reservation_time),
        "reservation_end_time": str(doc.reservation_end_time),
    }


# ══════════════════════════════════════════════════
# UPDATE
# ══════════════════════════════════════════════════

@frappe.whitelist()
def update_reservation(name, **kwargs):
    """
    Update an existing booking.
    Only updates fields that are explicitly passed.
    """
    require_restaurant_user()
    doc = frappe.get_doc("Restaurant Booking", name)

    updatable = [
        "customer", "customer_name", "guest_name", "contact_number",
        "email", "party_size", "reservation_date", "reservation_time",
        "duration", "table", "notes", "source", "status",
    ]

    changed = False
    for field in updatable:
        if field in kwargs and kwargs[field] is not None:
            doc.set(field, kwargs[field])
            changed = True

    if changed:
        doc.save()

    return {
        "name": doc.name,
        "status": doc.status,
        "table": doc.table,
    }


# ══════════════════════════════════════════════════
# STATUS ACTIONS
# ══════════════════════════════════════════════════

@frappe.whitelist()
def check_in_reservation(booking_name):
    """
    Mark guest as Seated (check-in).
    Called from the React form's "Check In Guest" button.
    """
    require_restaurant_user()
    doc = frappe.get_doc("Restaurant Booking", booking_name)
    doc.seat()

    return {
        "name": doc.name,
        "status": doc.status,
        "table": doc.table,
        "seated_time": str(doc.seated_time),
    }


@frappe.whitelist()
def complete_reservation(booking_name):
    """Mark reservation as completed (guest left)."""
    require_restaurant_user()
    doc = frappe.get_doc("Restaurant Booking", booking_name)
    doc.complete()
    return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def cancel_reservation(booking_name, reason=None):
    """Cancel a reservation."""
    require_restaurant_user()
    doc = frappe.get_doc("Restaurant Booking", booking_name)
    doc.cancel_booking(reason=reason)
    return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def mark_no_show(booking_name):
    """Mark as no-show."""
    require_restaurant_user()
    doc = frappe.get_doc("Restaurant Booking", booking_name)
    doc.mark_no_show()
    return {"name": doc.name, "status": doc.status}


# ══════════════════════════════════════════════════
# EARLY CHECK-IN
# ══════════════════════════════════════════════════

@frappe.whitelist()
def early_check_in(booking_name, new_table=None):
    """
    Handle early arrival.
    Optionally reassign to a different table if original is occupied.

    Returns early_by_minutes so the UI can show a warning.
    """
    require_restaurant_user()
    doc = frappe.get_doc("Restaurant Booking", booking_name)

    now = now_datetime()
    start = doc.get_start_datetime()
    diff_minutes = (start - now).total_seconds() / 60

    if diff_minutes > 30:
        frappe.msgprint(
            _("Guest is {0} minutes early").format(int(diff_minutes)),
            indicator="orange",
            alert=True,
        )

    if new_table:
        doc.table = new_table

    doc.seat()

    return {
        "name": doc.name,
        "status": doc.status,
        "table": doc.table,
        "early_by_minutes": max(0, int(diff_minutes)),
    }


# ══════════════════════════════════════════════════
# SEARCH
# ══════════════════════════════════════════════════

@frappe.whitelist()
def search_reservation(query, restaurant=None, date=None):
    """
    Search bookings by customer name, guest name, phone, or booking ID.
    Used by the "I Have a Reservation" flow.

    Returns list of matching bookings (max 10).
    """
    require_restaurant_user()
    if not query or len(query) < 2:
        return []

    conditions = ["status IN ('Open', 'Confirmed', 'Waitlisted')"]
    params = {}

    # Search by booking ID (exact match)
    if query.upper().startswith("RES-BOOK"):
        conditions.append("name = %(query_exact)s")
        params["query_exact"] = query
    else:
        # Fuzzy search on name/phone
        conditions.append(
            "(customer_name LIKE %(q)s OR guest_name LIKE %(q)s OR contact_number LIKE %(q)s)"
        )
        params["q"] = "%{0}%".format(query)

    """ if restaurant:
        conditions.append("restaurant = %(restaurant)s")
        params["restaurant"] = restaurant """

    if date:
        conditions.append("reservation_date = %(date)s")
        params["date"] = date

    where = " AND ".join(conditions)

    results = frappe.db.sql(
        """
        SELECT
            name, status, customer, customer_name, guest_name,
            contact_number, party_size, reservation_date,
            reservation_time, reservation_end_time, duration,
            `table`, room, notes, source
        FROM `tabRestaurant Booking`
        WHERE {where}
        ORDER BY reservation_date ASC, reservation_time ASC
        LIMIT 10
        """.format(where=where),
        params,
        as_dict=True,
    )

    return results


# ══════════════════════════════════════════════════
# DASHBOARD / SUMMARY
# ══════════════════════════════════════════════════

@frappe.whitelist()
def get_daily_summary(restaurant, date=None):
    """
    Summary stats for a day. Used for dashboard display.

    Returns:
        {
            date, total_bookings, total_guests,
            by_status: { "Confirmed": { count, guests }, ... },
            upcoming: [ ... next 5 bookings ... ]
        }
    """
    require_restaurant_user()
    date = date or today()

    stats = frappe.db.sql(
        """
        SELECT status, COUNT(*) as cnt, SUM(party_size) as guests
        FROM `tabRestaurant Booking`
        WHERE reservation_date = %(date)s
        GROUP BY status
        """,
        {"date": date},
        as_dict=True,
    )

    summary = {
        "date": date,
        "total_bookings": 0,
        "total_guests": 0,
        "by_status": {},
    }

    for s in stats:
        summary["by_status"][s.status] = {
            "count": cint(s.cnt),
            "guests": cint(s.guests),
        }
        if s.status not in ("Cancelled", "No Show"):
            summary["total_bookings"] += cint(s.cnt)
            summary["total_guests"] += cint(s.guests)

    # Next upcoming
    now = now_datetime()
    upcoming = frappe.db.sql(
        """
        SELECT name, customer_name, guest_name, party_size,
               reservation_time, `table`, status
        FROM `tabRestaurant Booking`
        WHERE reservation_date = %(date)s
          AND status IN ('Open', 'Confirmed')
          AND reservation_time >= %(time)s
        ORDER BY reservation_time ASC
        LIMIT 5
        """,
        {"date": date, "time": now.strftime("%H:%M:%S")},
        as_dict=True,
    )
    summary["upcoming"] = upcoming

    return summary


@frappe.whitelist()
def get_reservations(restaurant, date, status=None):
    """
    Get all reservations for a date. Used by timeline/calendar views.

    Optional status filter: comma-separated string e.g. "Open,Confirmed,Seated"
    """
    require_restaurant_user()
    filters = {
        #"restaurant": restaurant,
        "company": frappe.defaults.get_user_default('company'),
        "reservation_date": getdate(date),
    }

    if status:
        filters["status"] = ["in", [s.strip() for s in status.split(",")]]

    return frappe.get_all(
        "Restaurant Booking",
        filters=filters,
        fields=[
            "name", "status", "customer", "customer_name", "guest_name",
            "contact_number", "party_size", "reservation_date",
            "reservation_time", "reservation_end_time", "duration",
            "table", "room", "floor", "notes", "source", "color",
            "seated_time", "completed_time",
        ],
        order_by="reservation_time asc",
    )


# ══════════════════════════════════════════════════
# UTILITY (not whitelisted)
# ══════════════════════════════════════════════════

def get_table_conflicts(table, date, time_start, time_end, exclude=None):
    """
    Find reservations that overlap with a requested time range.

    Overlap logic: existing_start < requested_end AND existing_end > requested_start

    Returns list of conflicting booking dicts.
    """
    filters = {
        "table": table,
        "reservation_date": getdate(date),
        "status": ["in", ["Open", "Confirmed", "Waitlisted", "Seated"]],
    }
    if exclude:
        filters["name"] = ["!=", exclude]

    bookings = frappe.get_all(
        "Restaurant Booking",
        filters=filters,
        fields=[
            "name", "reservation_time", "reservation_end_time",
            "customer_name", "guest_name", "party_size", "status",
        ],
    )

    req_start = get_time(time_start)
    req_end = get_time(time_end)

    return [
        b
        for b in bookings
        if get_time(b.reservation_time) < req_end
        and get_time(b.reservation_end_time) > req_start
    ]


def auto_expire_no_shows():
    """
    Scheduled job: mark overdue reservations as No Show.

    Runs every 15 minutes. Marks as No Show if:
    - reservation_date = today
    - status is Open or Confirmed
    - reservation_end_time + 30min grace has passed

    Add to hooks.py scheduler_events:
        "cron": {
            "*/15 * * * *": [
                "restaurant_management.restaurant_management.api.booking.auto_expire_no_shows"
            ]
        }
    """
    now = now_datetime()
    grace_minutes = 30
    cutoff = (now - timedelta(minutes=grace_minutes)).time().strftime("%H:%M:%S")

    overdue = frappe.db.sql(
        """
        SELECT name
        FROM `tabRestaurant Booking`
        WHERE reservation_date = %(date)s
          AND status IN ('Open', 'Confirmed')
          AND reservation_end_time < %(cutoff)s
        """,
        {"date": now.date(), "cutoff": cutoff},
        as_dict=True,
    )

    for b in overdue:
        frappe.db.set_value("Restaurant Booking", b.name, "status", "No Show")

    if overdue:
        frappe.db.commit()
        frappe.logger().info("Auto-expired {0} bookings as No Show".format(len(overdue)))


# ══════════════════════════════════════════════════
# HOOK EVENT HANDLERS
# ══════════════════════════════════════════════════
# Referenced in hooks.py doc_events

def on_booking_update(doc, method):
    """Publish realtime event when any booking changes."""
    frappe.publish_realtime(
        "booking_update",
        {
            "name": doc.name,
            "status": doc.status,
            "table": doc.table,
            "reservation_date": str(doc.reservation_date),
            "action": "update",
        },
        after_commit=True,
    )


def on_booking_delete(doc, method):
    """Publish realtime event when a booking is deleted."""
    frappe.publish_realtime(
        "booking_update",
        {
            "name": doc.name,
            "table": doc.table,
            "reservation_date": str(doc.reservation_date),
            "action": "delete",
        },
        after_commit=True,
    )

    # Release table
    if doc.table:
        try:
            table = frappe.get_doc("Ren Table", doc.table)
            if hasattr(table, "_on_update"):
                table._on_update()
        except Exception:
            pass