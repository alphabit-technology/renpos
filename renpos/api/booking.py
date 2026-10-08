# -*- coding: utf-8 -*-
# renpos/api/booking.py
#
# Reservations: availability, slots and pacing, the host stand (today's
# list, waitlist, seating), guest messages and the scheduled jobs.
#
# Every rule comes from the restaurant's Ren Reservation Settings
# (table time by party size, grace, no-show, slots, pacing, hours, messages);
# a restaurant without settings gets the defaults in DEFAULT_POLICY.
#
# Times are the site's time zone (System Settings), like every Frappe
# datetime. A reservation occupies its tables from starts_at to ends_at
# (full datetimes, so parties that run past midnight work).

import frappe
from frappe import _
from frappe.utils import (
    add_to_date, cint, cstr, get_datetime, get_time, getdate, now_datetime, today,
)
from datetime import datetime, timedelta

from renpos.api.guards import require_restaurant_user, current_pos_profile, current_restaurant, is_manager


def _own_restaurant(restaurant):
    """Staff only see their own restaurant's bookings (managers: any)."""
    mine = current_restaurant()
    if restaurant and restaurant != mine and not is_manager():
        raise frappe.PermissionError(_("Not your restaurant"))
    return restaurant or mine


def _see():
    """Reading the host stand (reservations, waitlist, availability) needs "manage reservations" too."""
    from renpos.api import access
    require_restaurant_user()
    if not access.can("manage_reservations"):
        raise frappe.PermissionError(_("Your role doesn't handle reservations"))


def _manage(booking_restaurant=None):
    from renpos.api import access
    access.require("manage_reservations")
    if booking_restaurant:
        _own_restaurant(booking_restaurant)


# statuses that hold a table
HOLDING = ("Open", "Confirmed", "Seated")
# statuses still waiting for the guest
UPCOMING = ("Open", "Confirmed")
ACTIVE = ("Open", "Confirmed", "Waitlisted", "Seated")

# allowed status changes (None = new booking)
TRANSITIONS = {
    None: {"Open", "Confirmed", "Waitlisted", "Seated"},
    "Open": {"Confirmed", "Waitlisted", "Seated", "Cancelled", "No Show"},
    "Confirmed": {"Open", "Waitlisted", "Seated", "Cancelled", "No Show"},
    "Waitlisted": {"Open", "Confirmed", "Seated", "Cancelled", "No Show"},
    "Seated": {"Completed"},
    "No Show": {"Open", "Confirmed", "Seated"},     # the guest showed up after all / undo
    "Cancelled": {"Open", "Confirmed"},              # reinstate
    "Completed": set(),
}
# a manager can also undo a seating made by mistake
MANAGER_TRANSITIONS = {"Seated": {"Confirmed", "Open"}}

DEFAULT_POLICY = frappe._dict(
    enabled=1, max_party_size=12, min_advance_minutes=0, max_advance_days=60,
    default_duration=90, turn_times=[], late_grace_minutes=15, no_show_after_minutes=30,
    reserved_before_minutes=60, slot_minutes=15, max_covers_per_slot=0, opening_hours=[],
    send_confirmation=0, confirmation_template=None, send_reminder=0, reminder_hours_before=3,
    reminder_template=None, sms_enabled=0,
    waitlist_sms_message="Hi {guest}, your table at {restaurant} is ready. Please come to the host stand.",
)

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ══════════════════════════════════════════════════
# POLICY
# ══════════════════════════════════════════════════

def get_policy(restaurant=None):
    if restaurant and frappe.db.exists("Ren Reservation Settings", restaurant):
        doc = frappe.get_cached_doc("Ren Reservation Settings", restaurant)
        p = frappe._dict(DEFAULT_POLICY)
        p.update({k: doc.get(k) for k in DEFAULT_POLICY if k not in ("turn_times", "opening_hours")})
        p.turn_times = [frappe._dict(r.as_dict()) for r in doc.turn_times or []]
        p.opening_hours = [frappe._dict(r.as_dict()) for r in doc.opening_hours or []]
        p.name = doc.name
        return p
    return frappe._dict(DEFAULT_POLICY)


def duration_for(policy, party_size):
    size = cint(party_size)
    for row in policy.turn_times or []:
        if cint(row.min_party) <= size <= cint(row.max_party):
            return cint(row.minutes)
    return cint(policy.default_duration) or 90


def restaurant_of_table(table):
    if not table:
        return None
    row = frappe.db.sql(
        """SELECT f.restaurant, r.name, r.floor FROM `tabRen Table` t JOIN `tabRen Room` r ON r.name = t.room
        JOIN `tabRen Floor` f ON f.name = r.floor WHERE t.name = %s""", table)
    return row[0][0] if row else None


def _to_dt(date, time):
    return datetime.combine(getdate(date), get_time(time))


def is_open_at(policy, start):
    """Whether `start` (datetime) is within the reservation hours."""
    rows = policy.opening_hours or []
    if not rows:
        return True
    t = start.time()
    day = WEEKDAYS[start.weekday()]
    prev = WEEKDAYS[(start.weekday() - 1) % 7]
    for r in rows:
        opens, closes = get_time(r.opens), get_time(r.closes)
        overnight = closes < opens
        if r.weekday == day and t >= opens and (overnight or t <= closes):
            return True
        if r.weekday == prev and overnight and t <= closes:
            return True
    return False


# ══════════════════════════════════════════════════
# TABLES & CONFLICTS
# ══════════════════════════════════════════════════

def booking_tables(doc):
    tables = [doc.get("table")] if doc.get("table") else []
    for row in doc.get("extra_tables") or []:
        t = row.get("table") if isinstance(row, dict) else row.table
        if t and t not in tables:
            tables.append(t)
    return tables


def holding_bookings(tables, start, end, exclude=None):
    """Bookings that hold any of `tables` at some point between start and end."""
    if not tables:
        return []
    return frappe.db.sql(
        """
        SELECT DISTINCT b.name, b.starts_at, b.ends_at, b.customer_name, b.guest_name, b.party_size, b.status,
               b.`table`
        FROM `tabRen Booking` b
        LEFT JOIN `tabRen Booking Table` x ON x.parent = b.name AND x.parenttype = 'Ren Booking'
        WHERE b.status IN %(holding)s AND b.starts_at < %(end)s AND b.ends_at > %(start)s
          AND (b.`table` IN %(tables)s OR x.`table` IN %(tables)s)
          AND b.name != %(exclude)s
        ORDER BY b.starts_at
        """,
        {"holding": HOLDING, "start": start, "end": end, "tables": list(tables), "exclude": exclude or ""},
        as_dict=True,
    )


def tables_with_open_orders(tables, exclude_order=None):
    if not tables:
        return set()
    filters = {"table": ["in", list(tables)], "status": ["not in", ["Invoiced", "Cancelled"]]}
    if exclude_order:
        filters["name"] = ["!=", exclude_order]
    return set(frappe.get_all("Ren Order", filters=filters, pluck="table"))


def _guest(b):
    return b.get("customer_name") or b.get("guest_name") or _("another guest")


def _restaurant_tables(restaurant):
    return frappe.db.sql(
        """
        SELECT t.name, t.description AS table_name, t.no_of_seats AS capacity, t.minimum_seating,
               t.room, r.description AS room_name, r.floor
        FROM `tabRen Table` t
        LEFT JOIN `tabRen Room` r ON r.name = t.room
        LEFT JOIN `tabRen Floor` f ON f.name = r.floor
        WHERE (%(restaurant)s IS NULL OR f.restaurant = %(restaurant)s)
        ORDER BY r.description, t.description
        """,
        {"restaurant": restaurant},
        as_dict=True,
    )


# ══════════════════════════════════════════════════
# AVAILABILITY & SLOTS
# ══════════════════════════════════════════════════

@frappe.whitelist()
def get_policy_info(restaurant=None):
    """What the reservation form needs: table times, slot size, limits, hours."""
    _see()
    restaurant = _own_restaurant(restaurant)
    p = get_policy(restaurant)
    return {
        "restaurant": restaurant,
        "configured": bool(p.get("name")),
        "default_duration": cint(p.default_duration),
        "turn_times": [{"min_party": r.min_party, "max_party": r.max_party, "minutes": r.minutes}
                       for r in p.turn_times],
        "slot_minutes": cint(p.slot_minutes) or 15,
        "max_party_size": cint(p.max_party_size),
        "late_grace_minutes": cint(p.late_grace_minutes),
        "max_advance_days": cint(p.max_advance_days),
        "now": now_datetime(),
        "today": today(),
    }


@frappe.whitelist()
def get_table_availability(date, time_start, time_end=None, party_size=0, duration=None, exclude=None):
    """
    Tables of the user's restaurant with their availability for a time:
    [{name, table_name, capacity, room, room_name, available, status_indicator
      (green | red | gray), conflict_info}]
    """
    _see()
    restaurant = current_restaurant()
    policy = get_policy(restaurant)
    party_size = cint(party_size)
    start = _to_dt(date, time_start)
    if duration:
        end = start + timedelta(minutes=cint(duration))
    elif time_end:
        end = _to_dt(date, time_end)
        if end <= start:
            end += timedelta(days=1)
    else:
        end = start + timedelta(minutes=duration_for(policy, party_size))

    tables = _restaurant_tables(restaurant)
    names = [t.name for t in tables]
    holding = holding_bookings(names, start, end, exclude=exclude)
    by_table = {}
    for b in holding:
        if b.table:
            by_table.setdefault(b.table, []).append(b)
    # extra tables of combined bookings
    for row in frappe.get_all("Ren Booking Table", filters={"parent": ["in", [b.name for b in holding] or [""]]},
                              fields=["parent", "table"]):
        b = next(x for x in holding if x.name == row.parent)
        if b not in by_table.get(row.table, []):
            by_table.setdefault(row.table, []).append(b)
    busy_now = tables_with_open_orders(names) if start <= now_datetime() + timedelta(minutes=30) else set()

    for t in tables:
        t["room_name"] = t.room_name or t.room or ""
        conflicts = by_table.get(t.name, [])
        if conflicts:
            c = conflicts[0]
            t.update(available=False, status_indicator="red", conflict_info="{0} ({1})  {2}-{3}".format(
                _guest(c), c.party_size, get_datetime(c.starts_at).strftime("%H:%M"),
                get_datetime(c.ends_at).strftime("%H:%M")))
        elif t.name in busy_now:
            t.update(available=False, status_indicator="red", conflict_info=_("Occupied now"))
        elif party_size and cint(t.capacity) and cint(t.capacity) < party_size:
            t.update(available=False, status_indicator="gray",
                     conflict_info=_("Seats {0}, party of {1}").format(t.capacity, party_size))
        else:
            t.update(available=True, status_indicator="green", conflict_info="")
    return tables


@frappe.whitelist()
def get_slots(date, party_size=2, restaurant=None, exclude=None):
    """
    Bookable times for a date and party size:
    [{time, available (bool), tables (n free that fit), covers (guests
      arriving in that slot), reason}]
    """
    _see()
    return compute_slots(date, party_size, _own_restaurant(restaurant), exclude)


def compute_slots(date, party_size, restaurant, exclude=None, with_tables=False):
    policy = get_policy(restaurant)
    party = cint(party_size) or 2
    duration = duration_for(policy, party)
    step = cint(policy.slot_minutes) or 15
    day = getdate(date)
    now = now_datetime()

    tables = [t for t in _restaurant_tables(restaurant) if not cint(t.capacity) or cint(t.capacity) >= party]
    names = [t.name for t in tables]
    day_start = datetime.combine(day, datetime.min.time())
    window_end = day_start + timedelta(days=1, minutes=duration)
    holding = holding_bookings([t.name for t in _restaurant_tables(restaurant)] or [""], day_start, window_end,
                               exclude=exclude)
    extra = {}
    for row in frappe.get_all("Ren Booking Table", filters={"parent": ["in", [b.name for b in holding] or [""]]},
                              fields=["parent", "table"]):
        extra.setdefault(row.parent, []).append(row.table)
    max_covers = cint(policy.max_covers_per_slot)
    # guests arriving per slot: every upcoming booking of the restaurant (with or without table),
    # the same count the save-time pacing check uses
    arrivals = frappe.db.sql(
        """SELECT starts_at, party_size FROM `tabRen Booking`
        WHERE status IN ('Open', 'Confirmed') AND starts_at >= %(s)s AND starts_at < %(e)s
          AND IFNULL(restaurant, '') = %(r)s AND name != %(x)s""",
        {"s": day_start, "e": day_start + timedelta(days=1), "r": restaurant or "", "x": exclude or ""},
        as_dict=True)
    # tables with people at them now (walk-ins, parties still eating)
    occupied_now = tables_with_open_orders(names)

    slots = []
    t = day_start
    while t < day_start + timedelta(days=1):
        slot = {"time": t.strftime("%H:%M"), "available": True, "tables": 0, "covers": 0, "reason": ""}
        end = t + timedelta(minutes=duration)
        if not is_open_at(policy, t):
            t += timedelta(minutes=step)
            continue
        if t < now + timedelta(minutes=cint(policy.min_advance_minutes)):
            slot.update(available=False, reason=_("Past"))
        busy = set()
        for b in holding:
            if get_datetime(b.starts_at) < end and get_datetime(b.ends_at) > t:
                busy.add(b.table)
                busy.update(extra.get(b.name, []))
        if t < now + timedelta(minutes=duration):
            busy |= occupied_now
        slot["covers"] = sum(cint(a.party_size) for a in arrivals
                             if t <= get_datetime(a.starts_at) < t + timedelta(minutes=step))
        free = [n for n in names if n not in busy]
        slot["tables"] = len(free)
        if with_tables:
            slot["free_tables"] = free
        if slot["available"] and not slot["tables"]:
            slot.update(available=False, reason=_("No table"))
        if slot["available"] and max_covers and slot["covers"] + party > max_covers:
            slot.update(available=False, reason=_("Kitchen pacing"))
        slots.append(slot)
        t += timedelta(minutes=step)
    return {"duration": duration, "slots": slots}


# ══════════════════════════════════════════════════
# CREATE / UPDATE
# ══════════════════════════════════════════════════

FORM_FIELDS = (
    "customer", "customer_name", "guest_name", "contact_number", "email", "party_size", "reservation_date",
    "reservation_time", "duration", "table", "notes", "internal_notes", "source", "quoted_wait",
)


@frappe.whitelist()
def create_reservation(**kwargs):
    """New reservation from the host stand. extra_tables: JSON list of table names."""
    require_restaurant_user()
    _manage()
    if not kwargs.get("customer") and not kwargs.get("guest_name"):
        frappe.throw(_("Please provide a Customer or Guest Name"))
    doc = frappe.new_doc("Ren Booking")
    for f in FORM_FIELDS:
        if kwargs.get(f) not in (None, ""):
            doc.set(f, kwargs.get(f))
    doc.party_size = cint(kwargs.get("party_size")) or 2
    doc.source = kwargs.get("source") or "Phone"
    doc.pos_profile = kwargs.get("pos_profile") or current_pos_profile()
    _set_extra_tables(doc, kwargs.get("extra_tables"))
    doc.flags.ignore_permissions = True
    doc.insert()
    _own_restaurant(doc.restaurant)
    return booking_dict(doc)


@frappe.whitelist()
def update_reservation(name, **kwargs):
    """Edit details. Status changes go through the action endpoints."""
    require_restaurant_user()
    doc = frappe.get_doc("Ren Booking", name)
    doc.check_permission("read")
    _manage(doc.restaurant)
    doc.flags.ignore_permissions = True
    for f in FORM_FIELDS:
        if f in kwargs and kwargs[f] is not None:
            doc.set(f, kwargs[f])
    if "extra_tables" in kwargs:
        _set_extra_tables(doc, kwargs.get("extra_tables"))
    doc.save()
    return booking_dict(doc)


def _set_extra_tables(doc, value):
    if value is None:
        return
    tables = frappe.parse_json(value) if isinstance(value, str) else value
    doc.set("extra_tables", [{"table": t} for t in (tables or []) if t and t != doc.table])


def booking_dict(doc):
    policy = get_policy(doc.restaurant)
    d = {f: doc.get(f) for f in (
        "name", "status", "customer", "customer_name", "guest_name", "contact_number", "email", "party_size",
        "reservation_date", "reservation_time", "reservation_end_time", "duration", "table", "room", "floor",
        "notes", "internal_notes", "source", "starts_at", "ends_at", "seated_time", "completed_time",
        "table_order", "quoted_wait", "notified_at", "creation",
    )}
    d["extra_tables"] = [r.table for r in doc.extra_tables or []]
    for f in ("reservation_time", "reservation_end_time"):
        if d.get(f) is not None:
            d[f] = get_time(d[f]).strftime("%H:%M:%S")
    d["late"] = bool(doc.status in UPCOMING and doc.starts_at and now_datetime()
                     > get_datetime(doc.starts_at) + timedelta(minutes=cint(policy.late_grace_minutes)))
    return d


# ══════════════════════════════════════════════════
# STATUS ACTIONS
# ══════════════════════════════════════════════════

def _get(name):
    require_restaurant_user()
    doc = frappe.get_doc("Ren Booking", name)
    doc.check_permission("read")
    _manage(doc.restaurant)
    doc.flags.ignore_permissions = True
    return doc


@frappe.whitelist()
def check_in_reservation(booking_name, table=None, extra_tables=None, create_order=1):
    """
    Seat the party: on its table or another one (table / extra_tables),
    and open the table's order with the guest and party size. Works for
    early, on-time and late arrivals.
    """
    doc = _get(booking_name)
    if extra_tables is not None:
        _set_extra_tables(doc, extra_tables)
    order = doc.seat(table=table, create_order=cint(create_order))
    return {**booking_dict(doc), "order": order}


@frappe.whitelist()
def complete_reservation(booking_name):
    doc = _get(booking_name)
    doc.complete()
    return booking_dict(doc)


@frappe.whitelist()
def cancel_reservation(booking_name, reason=None):
    doc = _get(booking_name)
    doc.cancel_booking(reason=reason)
    return booking_dict(doc)


@frappe.whitelist()
def mark_no_show(booking_name):
    doc = _get(booking_name)
    doc.mark_no_show()
    return booking_dict(doc)


@frappe.whitelist()
def set_status(booking_name, status):
    """Reinstate / undo (validated by the booking's status rules)."""
    doc = _get(booking_name)
    if status == "Seated":
        frappe.throw(_("Use Seat to seat a party"))
    doc.status = status
    doc.save()
    return booking_dict(doc)


# ══════════════════════════════════════════════════
# WAITLIST
# ══════════════════════════════════════════════════

@frappe.whitelist()
def add_to_waitlist(guest_name=None, party_size=2, contact_number=None, quoted_wait=None, notes=None,
                    customer=None):
    require_restaurant_user()
    _manage()
    if not guest_name and not customer:
        frappe.throw(_("Please provide a name"))
    now = now_datetime()
    doc = frappe.get_doc({
        "doctype": "Ren Booking", "status": "Waitlisted", "source": "Walk-in",
        "guest_name": guest_name, "customer": customer, "party_size": cint(party_size) or 2,
        "contact_number": contact_number, "notes": notes, "quoted_wait": cint(quoted_wait),
        "reservation_date": now.date(), "reservation_time": now.strftime("%H:%M:%S"),
        "pos_profile": current_pos_profile(),
    })
    doc.flags.ignore_permissions = True
    doc.insert()
    return booking_dict(doc)


@frappe.whitelist()
def notify_table_ready(booking_name):
    """Text the waiting party that their table is ready (SMS Settings)."""
    doc = _get(booking_name)
    if doc.status != "Waitlisted":
        frappe.throw(_("Only waiting parties can be notified"))
    policy = get_policy(doc.restaurant)
    sent = send_guest_message(doc, "table_ready", policy)
    doc.db_set("notified_at", now_datetime())
    _publish(doc)
    return {"sent": sent, **booking_dict(doc)}


# ══════════════════════════════════════════════════
# HOST STAND
# ══════════════════════════════════════════════════

@frappe.whitelist()
def get_day(date=None, restaurant=None):
    """
    Everything the host stand shows for a day: reservations (with late flag
    and guest history), the waitlist and the tables for the timeline.
    """
    _see()
    restaurant = _own_restaurant(restaurant)
    policy = get_policy(restaurant)
    day = getdate(date or today())
    start = datetime.combine(day, datetime.min.time())
    names = frappe.db.sql(
        """SELECT name FROM `tabRen Booking`
        WHERE ((starts_at >= %(start)s AND starts_at < %(end)s) OR (reservation_date = %(day)s))
          AND (%(restaurant)s IS NULL OR IFNULL(restaurant, '') IN ('', %(restaurant)s))
        ORDER BY starts_at""",
        {"start": start, "end": start + timedelta(days=1), "day": day, "restaurant": restaurant},
        pluck=True,
    )
    bookings = [booking_dict(frappe.get_doc("Ren Booking", n)) for n in names]
    history = guest_histories(bookings)
    for b in bookings:
        b["guest"] = history.get(b["customer"] or b["contact_number"] or "", {})
    summary = {
        "reservations": len([b for b in bookings if b["status"] in ("Open", "Confirmed", "Seated", "Completed")]),
        "covers": sum(cint(b["party_size"]) for b in bookings if b["status"] in ("Open", "Confirmed", "Seated",
                                                                                "Completed")),
        "seated": len([b for b in bookings if b["status"] == "Seated"]),
        "waiting": len([b for b in bookings if b["status"] == "Waitlisted"]),
        "no_shows": len([b for b in bookings if b["status"] == "No Show"]),
    }
    return {
        "date": day,
        "now": now_datetime(),
        "summary": summary,
        "bookings": bookings,
        "tables": _restaurant_tables(restaurant),
        "busy_tables": list(tables_with_open_orders([t.name for t in _restaurant_tables(restaurant)])),
        "policy": {"late_grace_minutes": cint(policy.late_grace_minutes), "slot_minutes": cint(policy.slot_minutes),
                   "sms": cint(policy.sms_enabled)},
    }


def guest_histories(bookings):
    """{customer or phone: {visits, no_shows, cancellations, last_visit, tags, guest_notes}}"""
    keys_c = {b["customer"] for b in bookings if b.get("customer")}
    keys_p = {b["contact_number"] for b in bookings if b.get("contact_number") and not b.get("customer")}
    out = {}
    if keys_c:
        for r in frappe.db.sql(
            """SELECT customer AS k, SUM(status='Completed') AS visits, SUM(status='No Show') AS no_shows,
                      SUM(status='Cancelled') AS cancellations, MAX(IF(status='Completed', starts_at, NULL)) AS last_visit
            FROM `tabRen Booking` WHERE customer IN %(k)s GROUP BY customer""", {"k": list(keys_c)},
            as_dict=True):
            out[r.k] = r
        meta = frappe.get_meta("Customer")
        if meta.has_field("ren_guest_tags"):
            for c in frappe.get_all("Customer", filters={"name": ["in", list(keys_c)]},
                                    fields=["name", "ren_guest_tags", "ren_guest_notes"]):
                out.setdefault(c.name, frappe._dict()).update(tags=c.ren_guest_tags, guest_notes=c.ren_guest_notes)
    if keys_p:
        for r in frappe.db.sql(
            """SELECT contact_number AS k, SUM(status='Completed') AS visits, SUM(status='No Show') AS no_shows,
                      SUM(status='Cancelled') AS cancellations, MAX(IF(status='Completed', starts_at, NULL)) AS last_visit
            FROM `tabRen Booking` WHERE contact_number IN %(k)s GROUP BY contact_number""",
            {"k": list(keys_p)}, as_dict=True):
            out[r.k] = r
    for v in out.values():
        for f in ("visits", "no_shows", "cancellations"):
            v[f] = cint(v.get(f))
    return out


@frappe.whitelist()
def search_reservation(query, restaurant=None, date=None):
    """Search active bookings by guest name, phone or booking ID (max 10)."""
    _see()
    if not query or len(query) < 2:
        return []
    restaurant = _own_restaurant(restaurant)
    params = {"q": "%{0}%".format(query), "exact": query, "restaurant": restaurant, "date": date}
    rows = frappe.db.sql(
        """SELECT name FROM `tabRen Booking`
        WHERE status IN ('Open', 'Confirmed', 'Waitlisted', 'No Show')
          AND (name = %(exact)s OR customer_name LIKE %(q)s OR guest_name LIKE %(q)s OR contact_number LIKE %(q)s)
          AND (%(restaurant)s IS NULL OR IFNULL(restaurant, '') IN ('', %(restaurant)s))
          AND (%(date)s IS NULL OR reservation_date = %(date)s)
          AND reservation_date >= %(from)s
        ORDER BY starts_at LIMIT 10""",
        {**params, "from": add_to_date(today(), days=-1)}, pluck=True,
    )
    return [booking_dict(frappe.get_doc("Ren Booking", n)) for n in rows]


# ══════════════════════════════════════════════════
# GUEST MESSAGES
# ══════════════════════════════════════════════════

DEFAULT_MESSAGES = {
    "confirmation": (
        "Your reservation at {restaurant} is confirmed",
        "Hi {guest},\n\nYour table for {party_size} at {restaurant} is confirmed for {date} at {time}.\n"
        "Reference: {name}\n\nSee you soon!",
    ),
    "reminder": (
        "Reminder: your reservation at {restaurant}",
        "Hi {guest},\n\nA reminder of your table for {party_size} at {restaurant} on {date} at {time}.\n"
        "Reference: {name}",
    ),
}


class _SafeDict(dict):
    def __missing__(self, key):
        return ""


def _context(doc, html=False):
    """Plain values for messages. `html`: escaped, for email bodies (guests type their own names)."""
    start = get_datetime(doc.starts_at) if doc.starts_at else _to_dt(doc.reservation_date, doc.reservation_time)
    ctx = {
        "guest": doc.customer_name or doc.guest_name or "",
        "restaurant": frappe.db.get_value("Ren Restaurant", doc.restaurant, "restaurant_name") or doc.restaurant or "",
        "party_size": cstr(doc.party_size), "date": frappe.utils.formatdate(start.date()),
        "time": start.strftime("%I:%M %p").lstrip("0"), "name": doc.name,
    }
    if html:
        ctx = {k: frappe.utils.escape_html(v) for k, v in ctx.items()}
    return _SafeDict(ctx)


def _fill(template, ctx):
    try:
        return cstr(template).format_map(ctx)
    except (ValueError, IndexError, AttributeError):
        return cstr(template)


def send_guest_message(doc, kind, policy=None):
    """Email (Email Template or the default text) and SMS when enabled. Returns what was sent."""
    policy = policy or get_policy(doc.restaurant)
    ctx = _context(doc)
    sent = []
    if kind in ("confirmation", "reminder") and doc.email:
        template = policy.get(f"{kind}_template")
        if template:
            t = frappe.get_doc("Email Template", template)
            jctx = {**_context(doc, html=True), "doc": doc}
            subject = frappe.render_template(t.subject or "", {**ctx, "doc": doc})
            body = frappe.render_template(t.response_html if t.use_html else t.response, jctx)
        else:
            subject = _fill(DEFAULT_MESSAGES[kind][0], ctx)
            body = _fill(DEFAULT_MESSAGES[kind][1], _context(doc, html=True)).replace("\n", "<br>")
        frappe.sendmail(recipients=[doc.email], subject=subject, message=body,
                        reference_doctype=doc.doctype, reference_name=doc.name)
        sent.append("email")
    if cint(policy.sms_enabled) and doc.contact_number:
        if kind == "table_ready":
            msg = _fill(policy.waitlist_sms_message or DEFAULT_POLICY.waitlist_sms_message, ctx)
        else:
            msg = _fill(DEFAULT_MESSAGES[kind][1].split("\n\n")[1], ctx)
        frappe.enqueue("renpos.api.booking._send_sms", number=doc.contact_number, message=msg,
                       enqueue_after_commit=True)
        sent.append("sms")
    return sent


def _send_sms(number, message):
    try:
        from frappe.core.doctype.sms_settings.sms_settings import send_sms
        send_sms([number], message)
    except Exception:
        frappe.log_error(title="Restaurant: reservation SMS not sent")


# ══════════════════════════════════════════════════
# SCHEDULED JOBS (every 5 minutes)
# ══════════════════════════════════════════════════

def run_scheduled():
    auto_expire_no_shows()
    send_reminders()
    refresh_reserved_tables()


def auto_expire_no_shows():
    """Upcoming reservations not seated `no_show_after_minutes` after their time become No Show."""
    now = now_datetime()
    rows = frappe.db.sql(
        """SELECT name, restaurant, starts_at FROM `tabRen Booking`
        WHERE status IN ('Open', 'Confirmed') AND starts_at < %(now)s AND starts_at > %(since)s
          AND IFNULL(keep_until_seated, 0) = 0""",
        {"now": now, "since": now - timedelta(days=2)}, as_dict=True,
    )
    policies = {}
    for r in rows:
        p = policies.setdefault(r.restaurant, get_policy(r.restaurant))
        after = cint(p.no_show_after_minutes)
        if not after or now < get_datetime(r.starts_at) + timedelta(minutes=after):
            continue
        # only if nobody seated it meanwhile
        frappe.db.sql("""UPDATE `tabRen Booking` SET status = 'No Show', modified = %s
            WHERE name = %s AND status IN ('Open', 'Confirmed')""", (now, r.name))
        if not frappe.db.sql("SELECT ROW_COUNT()")[0][0]:
            continue
        doc = frappe.get_doc("Ren Booking", r.name)
        doc.add_comment("Info", _("Marked No Show automatically"))
        doc.refresh_tables()
        _publish(doc)
    frappe.db.commit()


def send_reminders():
    now = now_datetime()
    rows = frappe.db.sql(
        """SELECT name, restaurant, starts_at FROM `tabRen Booking`
        WHERE status IN ('Open', 'Confirmed') AND IFNULL(reminded, 0) = 0
          AND (IFNULL(email, '') != '' OR IFNULL(contact_number, '') != '')
          AND starts_at > %(now)s AND starts_at < %(until)s""",
        {"now": now, "until": now + timedelta(days=2)}, as_dict=True,
    )
    for r in rows:
        p = get_policy(r.restaurant)
        if not cint(p.send_reminder):
            continue
        window_start = get_datetime(r.starts_at) - timedelta(hours=cint(p.reminder_hours_before) or 3)
        if now < window_start:
            continue
        if get_datetime(frappe.db.get_value("Ren Booking", r.name, "creation")) > window_start:
            frappe.db.set_value("Ren Booking", r.name, "reminded", 1, update_modified=False)
            continue  # booked inside the window: the confirmation is enough
        doc = frappe.get_doc("Ren Booking", r.name)
        try:
            send_guest_message(doc, "reminder", p)
            doc.db_set("reminded", 1)
        except Exception:
            frappe.log_error(title="Restaurant: reservation reminder not sent", reference_doctype=doc.doctype,
                             reference_name=doc.name)
    frappe.db.commit()


def refresh_reserved_tables():
    """Tables entering or leaving their 'Reserved' window: refresh the floor plans."""
    now = now_datetime()
    rows = frappe.db.sql(
        """SELECT name FROM `tabRen Booking`
        WHERE status IN ('Open', 'Confirmed') AND IFNULL(`table`, '') != ''
          AND starts_at > %(from)s AND starts_at < %(to)s""",
        {"from": now - timedelta(hours=2), "to": now + timedelta(hours=3)}, pluck=True,
    )
    for n in rows:
        frappe.get_doc("Ren Booking", n).refresh_tables()


# ══════════════════════════════════════════════════
# HOOKS
# ══════════════════════════════════════════════════

def _publish(doc, action="update"):
    frappe.publish_realtime(
        "booking_update",
        {"name": doc.name, "status": doc.status, "table": doc.table, "reservation_date": str(doc.reservation_date),
         "action": action},
        after_commit=True,
    )


def on_booking_delete(doc, method):
    _publish(doc, "delete")
    doc.refresh_tables()


def _complete_quietly(name, unlink=False):
    """Never let the reservation stop a payment or a void."""
    try:
        b = frappe.get_doc("Ren Booking", name)
        b.flags.ignore_permissions = True
        if unlink:
            b.db_set("table_order", None)
        if b.status == "Seated":
            b.complete()
    except Exception:
        frappe.log_error(title="Restaurant: reservation not completed", reference_doctype="Ren Booking",
                         reference_name=name)


def on_table_order_update(doc, method):
    """The party paid: its reservation is completed."""
    if doc.status == "Invoiced":
        for name in frappe.get_all("Ren Booking", filters={"table_order": doc.name, "status": "Seated"},
                                   pluck="name"):
            _complete_quietly(name)


def on_table_order_trash(doc, method):
    for name in frappe.get_all("Ren Booking", filters={"table_order": doc.name}, pluck="name"):
        _complete_quietly(name, unlink=True)
