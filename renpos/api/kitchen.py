# -*- coding: utf-8 -*-
# renpos/api/kitchen.py
#
# Kitchen display (KDS) API for production centers (Ren Station).
#
# A production center is configured in its own form:
#   - Ren Station Item Group: item groups it handles (children included)
#   - Status Flow: its statuses in order, e.g. Sent -> Processing -> Ready
#   - optional restrictions by room / table
#   - Group Items By Order: one button per ticket instead of per line
#
# The status lives on each order line (Ren Order Item) and is shared by
# every center that handles it: a cafeteria moving a coffee Sent -> Delivering
# makes it appear at the dining room center (Delivering -> Delivered), and
# every screen showing that line refreshes in real time. Grouping by order is
# presentation only: a tap moves this center's lines of that ticket, never
# the order's own status, so centers never step on each other.
#
# Tickets are "rounds": the lines of an order sent together (same
# ordered_time). A second round of the same table is a new ticket.
#
# Which centers a user sees comes from the POS Profile (Restaurant
# Permission, per user): a floor grants its centers, or centers are granted
# one by one. Restaurant Managers see all of them.

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, get_fullname, now_datetime

from renpos.api.guards import require_restaurant_user, current_restaurant, is_manager
from renpos.api.modifiers import texts as modifier_texts
from renpos.api import parts as ren_parts
from renpos.api.statuses import editable_statuses

try:
    from frappe.realtime import get_doctype_room
    _ORDER_ROOM = get_doctype_room("Ren Order")
except ImportError:
    _ORDER_ROOM = "doctype:Ren Order"

VOIDS_VISIBLE_MINUTES = 15


class KitchenConflict(frappe.ValidationError):
    """Another screen changed the line first."""
    http_status_code = 409


# ─────────────────────────────────────────────
# Access
# ─────────────────────────────────────────────

def allowed_stations():
    """None = every station (managers, "Every production center"); otherwise the ones assigned in Ren Staff."""
    from renpos.api.access import can
    if is_manager() or can("all_stations"):
        return None
    return frappe.get_single("Ren Settings").restaurant_access("Ren Station") or set()


def _station(name):
    require_restaurant_user()
    if not name or not frappe.db.exists("Ren Station", name):
        frappe.throw(_("Production center {0} not found").format(name), frappe.DoesNotExistError)
    allowed = allowed_stations()
    if allowed is not None and name not in allowed:
        raise frappe.PermissionError(_("You don't have access to this production center"))
    return frappe.get_doc("Ren Station", name)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def ticket_key(row):
    """A round: the lines of one order sent together."""
    return f"{row.parent}::{row.ordered_time or ''}"


def _status_info(statuses):
    rows = frappe.get_all(
        "Ren Order Status",
        filters={"name": ["in", list(statuses) or [""]]},
        fields=["name", "color", "icon", "message", "action_message"],
    )
    return {r.name: r for r in rows}


def _rounds(orders):
    """{order: [ordered_time, ...]} of every round sent, to number the tickets."""
    if not orders:
        return {}
    rows = frappe.db.sql(
        """SELECT DISTINCT parent, ordered_time FROM `tabRen Order Item`
        WHERE parenttype = 'Ren Order' AND parent IN %(orders)s
          AND status NOT IN %(editable)s AND IFNULL(status, '') != '' AND ordered_time IS NOT NULL
        ORDER BY ordered_time""",
        {"orders": list(orders), "editable": editable_statuses()},
        as_dict=True,
    )
    out = {}
    for r in rows:
        out.setdefault(r.parent, []).append(str(r.ordered_time))
    return out


def _publish(st, rows, previous, new_status, extra=None):
    for order in {r.parent for r in rows}:
        mine = [r for r in rows if r.parent == order]
        payload = {
            "station": st.name,
            "order": order,
            "table": mine[0].table,
            "identifiers": [r.identifier for r in mine],
            "identifier": mine[0].identifier,
            "status": new_status,
            "previous_status": previous,
            "client_id": frappe.form_dict.get("client_id"),
            **(extra or {}),
        }
        frappe.publish_realtime("kitchen_update", payload, room=_ORDER_ROOM, after_commit=True)
        # waiters' order screens refresh the line status (a combo's line: its least advanced part)
        lines = {}
        for r in mine:
            status = (r.get("line_status") or frappe.db.get_value("Ren Order Item", r.name, "status")) \
                if r.get("part") else new_status
            lines.setdefault(status, []).append(r.get("line_identifier") or r.identifier)
        for status, identifiers in lines.items():
            frappe.publish_realtime(
                "order_update",
                {**payload, "identifiers": identifiers, "identifier": identifiers[0], "status": status,
                 "action": "update", "source": frappe.session.user},
                room=_ORDER_ROOM,
                after_commit=True,
            )


def _log(st, row, from_status, to_status):
    frappe.get_doc({
        "doctype": "Ren Kitchen Status Log",
        "changed_at": now_datetime(),
        "station": st.name,
        "from_status": from_status,
        "to_status": to_status,
        "user": frappe.session.user,
        "identifier": row.identifier,
        "order_name": row.parent,
        "item_code": row.item_code,
        "item_name": row.item_name,
        "qty": row.qty,
    }).insert(ignore_permissions=True)


def _set_status(rows, from_status, to_status):
    """Compare-and-set: only lines (or parts of a combo) still in from_status move."""
    whole = [r for r in rows if not r.get("part")]
    if whole:
        frappe.db.sql(
            """UPDATE `tabRen Order Item` SET status = %(to)s
            WHERE name IN %(names)s AND status = %(from)s""",
            {"to": to_status, "names": [r.name for r in whole], "from": from_status},
        )
    for r in rows:
        if r.get("part"):
            r.line_status = ren_parts.set_part_status(r.name, r.part, from_status, to_status)


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────

@frappe.whitelist()
def get_stations():
    """Production centers of the user's restaurant the user has access to."""
    require_restaurant_user()
    restaurant = current_restaurant()
    rows = frappe.db.sql(
        """
        SELECT s.name, s.description, s.floor, f.description AS floor_description,
               IFNULL(s.group_items_by_order, 0) AS group_items_by_order
        FROM `tabRen Station` s
        LEFT JOIN `tabRen Floor` f ON f.name = s.floor
        WHERE (%(restaurant)s IS NULL OR f.restaurant = %(restaurant)s)
        ORDER BY f.description, s.description
        """,
        {"restaurant": restaurant},
        as_dict=True,
    )
    allowed = allowed_stations()
    return rows if allowed is None else [r for r in rows if r.name in allowed]


@frappe.whitelist()
def get_floor_summary(floor):
    """
    What the floor plan's production dock shows for each center of a floor
    the user has access to: tickets waiting, how many are in each status of
    its flow (a ticket counts in its earliest status, as on the kitchen
    screen) and when the oldest one was sent.
    {server_time, stations: {station: {tickets, oldest, statuses: [{status, label, color, count}]}}}
    """
    require_restaurant_user()
    allowed = allowed_stations()
    out = {}
    for name in frappe.get_all("Ren Station", filters={"floor": floor}, pluck="name"):
        if allowed is not None and name not in allowed:
            continue
        st = frappe.get_doc("Ren Station", name)
        steps = st.flow
        order_of = {s: i for i, s in enumerate(steps)}
        earliest = {}
        oldest = None
        for i in st.queue_items():
            key = ticket_key(i)
            cur = earliest.get(key)
            if cur is None or order_of.get(i.status, 0) < order_of.get(cur, 0):
                earliest[key] = i.status
            if i.ordered_time and (oldest is None or i.ordered_time < oldest):
                oldest = i.ordered_time
        info = _status_info(steps)
        counts = {}
        for s in earliest.values():
            counts[s] = counts.get(s, 0) + 1
        out[name] = {
            "tickets": len(earliest),
            "oldest": oldest,
            "statuses": [
                {"status": s, "label": (info.get(s) or {}).get("message") or s,
                 "color": (info.get(s) or {}).get("color"), "count": counts[s]}
                for s in steps[:-1] if counts.get(s)
            ],
        }
    return {"server_time": now_datetime(), "stations": out}


@frappe.whitelist()
def get_station_queue(station):
    """
    Tickets waiting at a production center, oldest first. One ticket per
    round (lines of an order sent together):
    {station: {name, description, group_items_by_order, flow},
     tickets: [{key, order, round, table, ..., status, items: [{identifier,
                item_name, qty, modifiers, notes, status, next_status, ...}]}],
     voids: [lines voided in the last minutes that were waiting here]}
    A ticket's status is the earliest status among its lines; grouped
    centers also get its next_status / action (one button per ticket).
    """
    st = _station(station)
    grouped = cint(st.group_items_by_order)
    steps = st.flow
    flow = dict(zip(steps[:-1], steps[1:]))  # status -> next
    order_of = {s: i for i, s in enumerate(steps)}

    whole = grouped and cint(st.get("whole_order"))
    if whole:
        from renpos.api import dispatch
        followed = dispatch.order_lines(st)
        items = []
        info = _status_info(set(steps) | {r.status for r in followed if r.status})
        asks = {k for k, v in dispatch.status_meta(steps).items() if cint(v.ask_driver)}
    else:
        items = st.queue_items()
        info = _status_info(set(steps) | {i.status for i in items if i.status})
        asks = set()
    rounds = _rounds({i.parent for i in items})

    def status_block(status):
        s = info.get(status) or {}
        nxt = flow.get(status)
        return {
            "status": status,
            "color": s.get("color"),
            "message": s.get("message") or status,
            "next_status": nxt,
            # the button names the step it leads to: the next status's action ("Complete", "Deliver"...)
            "action": ((info.get(nxt) or {}).get("action_message") or nxt) if nxt else None,
            # moving into it asks who delivers (dispatch)
            "ask_driver": 1 if nxt and nxt in asks else 0,
        }

    if whole:
        return {
            "station": {"name": st.name, "description": st.description, "group_items_by_order": 1,
                        "whole_order": 1, "flow": steps},
            "server_time": now_datetime(),
            "tickets": dispatch.tickets(st, status_block, modifier_texts),
            "voids": recent_voids(st),
        }

    tickets = {}
    for i in items:
        key = ticket_key(i)
        t = tickets.get(key)
        if not t:
            order_rounds = rounds.get(i.parent) or []
            sent = str(i.ordered_time)
            t = tickets[key] = {
                "key": key,
                "order": i.parent,
                "short_name": i.parent[-5:],
                "round": order_rounds.index(sent) + 1 if sent in order_rounds else 1,
                "table": i.table,
                "table_description": i.table_description or i.table,
                "room_description": i.room_description,
                "dinners": i.dinners,
                "notes": i.order_notes,
                "server": get_fullname(i.order_owner) if i.order_owner else None,
                "ordered_time": i.ordered_time,
                "items": [],
            }
        t["items"].append({
            "identifier": i.identifier,
            "item_code": i.item_code,
            "item_name": i.item_name,
            "qty": i.qty,
            "notes": i.notes,
            "modifiers": modifier_texts(i.modifiers),
            "ordered_time": i.ordered_time,
            **status_block(i.status),
        })

    for t in tickets.values():
        earliest = min((it["status"] for it in t["items"]), key=lambda s: order_of.get(s, 0))
        if grouped:
            t.update(status_block(earliest))
        else:
            t["status"] = earliest

    return {
        "station": {
            "name": st.name, "description": st.description, "group_items_by_order": grouped, "flow": steps,
        },
        "server_time": now_datetime(),
        "tickets": sorted(tickets.values(), key=lambda t: str(t["ordered_time"] or "")),
        "voids": recent_voids(st),
    }


@frappe.whitelist()
def advance(station, identifier=None, ticket=None, expected=None, driver=None, driver_name=None):
    """
    Move a line (identifier), or this center's lines of a ticket (ticket key,
    for grouped centers: the lines at the ticket's earliest status), to the
    next status of the center's flow.

    `expected` is the status the screen showed: if another screen moved it
    first, nothing changes and a KitchenConflict (409) is raised, so a
    double tap never skips a step.
    """
    st = _station(station)
    if not identifier and not ticket:
        frappe.throw(_("Nothing to advance"))

    from renpos.api import dispatch
    orphans = []
    if ticket and ticket.endswith("::" + dispatch.ALL):
        # dispatch: the whole order, only once everything arrived
        current, rows, orphans = dispatch.rows_to_advance(st, ticket.partition("::")[0], expected)
        if not rows and not orphans:
            frappe.throw(_("This order is no longer waiting here; the screen will refresh"), KitchenConflict)
    elif ticket:
        order = ticket.partition("::")[0]
        rows = [r for r in st.queue_items("i.parent = %(order)s", {"order": order}, for_update=True)
                if ticket_key(r) == ticket]
        if not rows:
            frappe.throw(_("This ticket is no longer waiting here; the screen will refresh"), KitchenConflict)
        order_of = {s: i for i, s in enumerate(st.flow)}
        current = min((r.status for r in rows), key=lambda s: order_of.get(s, 0))
        rows = [r for r in rows if r.status == current]
    else:
        base, _option = ren_parts.split(identifier)
        rows = [r for r in st.queue_items("i.identifier = %(ident)s", {"ident": base}, for_update=True)
                if r.identifier == identifier]
        if not rows:
            frappe.throw(_("This item is no longer waiting here; the screen will refresh"), KitchenConflict)
        current = rows[0].status

    if expected and current != expected:
        frappe.throw(_("Another screen already moved it to {0}; the screen will refresh").format(_(current)),
                     KitchenConflict)

    new_status = st.next_status(current)
    orders = {r.parent for r in rows + orphans}
    if dispatch.needs_driver(new_status):
        dispatch.set_driver(orders, driver, driver_name)
    _set_status(rows, current, new_status)
    dispatch.move_orphans(orphans, new_status)
    rows = rows + orphans
    for r in rows:
        _log(st, r, current, new_status)
    dispatch.mark_finished(orders, new_status)

    _publish(st, rows, current, new_status)
    return {
        "identifier": identifier,
        "ticket": ticket,
        "identifiers": [r.identifier for r in rows],
        "status": new_status,
        "previous_status": current,
    }


@frappe.whitelist()
def get_recent(station, limit=20):
    """Recall: the last lines this center moved, newest first, and whether each can still be undone."""
    st = _station(station)
    logs = frappe.get_all(
        "Ren Kitchen Status Log",
        filters={"station": st.name, "undone": 0, "changed_at": [">=", add_to_date(now_datetime(), hours=-12)]},
        fields=["name", "changed_at", "from_status", "to_status", "user", "identifier", "order_name",
                "item_name", "qty"],
        order_by="changed_at desc, creation desc",
        limit=min(cint(limit) or 20, 100),
    )
    if not logs:
        return []
    current = {l.identifier: frappe._dict(status=ren_parts.current_status(l.identifier))
               for l in logs}
    current = {k: v for k, v in current.items() if v.status}
    tables = {
        o.name: o.table_description or o.table for o in frappe.get_all(
            "Ren Order", filters={"name": ["in", list({l.order_name for l in logs})]},
            fields=["name", "table", "table_description"],
        )
    }
    flow = st.flow
    seen, out = set(), []
    for l in logs:
        line = current.get(l.identifier)
        # only a line's latest move can be undone, and only while nothing moved it since
        can_undo = (bool(line) and line.status == l.to_status and l.identifier not in seen
                    and l.from_status in flow)
        seen.add(l.identifier)
        out.append({**l, "table": tables.get(l.order_name), "user_name": get_fullname(l.user),
                    "can_undo": can_undo})
    return out


@frappe.whitelist()
def undo(station, log):
    """Recall a line: put it back in the status it had before this center moved it."""
    st = _station(station)
    entry = frappe.get_doc("Ren Kitchen Status Log", log)
    if entry.station != st.name:
        raise frappe.PermissionError(_("This change was made at another production center"))
    if cint(entry.undone):
        frappe.throw(_("Already undone"), KitchenConflict)
    if entry.from_status not in st.flow:
        frappe.throw(_("Status {0} is not part of this center's flow").format(entry.from_status))
    base, option = ren_parts.split(entry.identifier)
    rows = frappe.db.sql(
        """SELECT i.name, i.identifier, i.item_code, i.item_name, i.qty, i.status, i.parent, o.table,
               i.ren_parts, i.ren_part_status
        FROM `tabRen Order Item` i JOIN `tabRen Order` o ON o.name = i.parent
        WHERE i.identifier = %(ident)s AND i.parenttype = 'Ren Order' FOR UPDATE""",
        {"ident": base},
        as_dict=True,
    )
    if option:
        rows = [r for r in ren_parts.expand(rows[0]) if r.part == option] if rows else []
    if not rows:
        frappe.throw(_("The item is no longer in the order"), KitchenConflict)
    if rows[0].status != entry.to_status:
        frappe.throw(_("The item was moved again ({0}); it can't be undone from here").format(_(rows[0].status)),
                     KitchenConflict)

    _set_status(rows, entry.to_status, entry.from_status)
    entry.db_set("undone", 1, update_modified=False)
    _publish(st, rows, entry.to_status, entry.from_status, {"recall": True})
    return {"identifier": entry.identifier, "status": entry.from_status}


def recent_voids(st, minutes=VOIDS_VISIBLE_MINUTES):
    """Lines voided in the last minutes that were waiting at this center."""
    statuses, groups = st.working_statuses, st._items_group
    if not statuses or not groups:
        return []
    rows = frappe.db.sql(
        """
        SELECT v.name, v.voided_at, v.void_type, v.reason, v.note, v.voided_by, v.order_name,
               v.table, v.item_name, v.qty, v.modifiers, v.status_at_void, t.room,
               IFNULL(t.description, v.table) AS table_description
        FROM `tabRen Void Log` v
        JOIN `tabItem` it ON it.name = v.item_code
        LEFT JOIN `tabRen Table` t ON t.name = v.table
        WHERE v.voided_at >= %(since)s AND v.status_at_void IN %(statuses)s AND it.item_group IN %(groups)s
        ORDER BY v.voided_at DESC
        """,
        {"since": add_to_date(now_datetime(), minutes=-minutes), "statuses": statuses, "groups": groups},
        as_dict=True,
    )
    rows = [r for r in rows if st.takes_order_from(r.room, r.table)]
    for r in rows:
        r["voided_by_name"] = get_fullname(r.voided_by)
    return rows
