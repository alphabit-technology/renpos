# -*- coding: utf-8 -*-
# restaurant_management/api/kitchen.py
#
# Kitchen display (KDS) API for production stations (Ren Station).
#
# A station is configured in its own form:
#   - Production Center Group: item groups it prepares (children included)
#   - Status Managed: the status flow it handles, e.g.
#         Sent -> Processing, Processing -> Completed
#   - optional restrictions by room / table / branch
#   - Group Items By Order: advance whole orders instead of single items
#
# Which items a station sees is decided by RenStation.get_command_filters(),
# the same rules the legacy kitchen screen used.

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from restaurant_management.api.guards import require_restaurant_user, current_pos_profile

try:
    from frappe.realtime import get_doctype_room
    _ORDER_ROOM = get_doctype_room("Table Order")
except ImportError:
    _ORDER_ROOM = "doctype:Table Order"


def _station(name):
    require_restaurant_user()
    station = frappe.get_doc("Ren Station", name)
    station.check_permission("read")
    return station


def _status_info(statuses):
    rows = frappe.get_all(
        "Status Order PC",
        filters={"name": ["in", list(statuses) or [""]]},
        fields=["name", "color", "icon", "message", "action_message"],
    )
    return {r.name: r for r in rows}


@frappe.whitelist()
def get_stations():
    """Production stations of the user's restaurant (all if it can't be resolved)."""
    require_restaurant_user()
    profile = current_pos_profile()
    restaurant = frappe.db.get_value("POS Profile", profile, "ren_restaurant") if profile else None
    return frappe.db.sql(
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


@frappe.whitelist()
def get_station_queue(station):
    """
    Tickets waiting at a station, oldest first:
    [{order, table, table_description, room_description, ordered_time,
      status, next_status, items: [{identifier, item_name, qty, notes,
      status, next_status, ordered_time}]}]
    """
    st = _station(station)
    grouped = cint(st.group_items_by_order)
    flow = {r.status_managed: r.next_status for r in st.status_managed}

    filters = st.get_command_filters()
    items = frappe.get_all(
        "Order Entry Item",
        filters=filters,
        fields=["identifier", "item_code", "item_name", "qty", "notes", "status",
                "parent", "ordered_time", "item_group"],
        order_by="ordered_time asc, idx asc",
    )

    parents = {i.parent for i in items}
    orders = {
        o.name: o for o in frappe.get_all(
            "Table Order",
            filters={"name": ["in", list(parents) or [""]]},
            fields=["name", "table", "table_description", "room_description",
                    "status", "dinners", "ordered_time", "notes"],
        )
    }

    statuses = set(flow) | set(flow.values()) | {i.status for i in items} \
        | {o.status for o in orders.values()}
    info = _status_info({s for s in statuses if s})

    def status_block(status):
        s = info.get(status) or {}
        nxt = flow.get(status)
        return {
            "status": status,
            "color": s.get("color"),
            "message": s.get("message") or status,
            "next_status": nxt,
            "action": (info.get(status) or {}).get("action_message") or nxt,
        }

    tickets = {}
    for i in items:
        order = orders.get(i.parent)
        if not order:
            continue
        t = tickets.get(i.parent)
        if not t:
            t = tickets[i.parent] = {
                "order": order.name,
                "short_name": order.name[-5:],
                "table": order.table,
                "table_description": order.table_description or order.table,
                "room_description": order.room_description,
                "dinners": order.dinners,
                "notes": order.notes,
                "ordered_time": i.ordered_time or order.ordered_time,
                **(status_block(order.status) if grouped else {}),
                "items": [],
            }
        t["items"].append({
            "identifier": i.identifier,
            "item_code": i.item_code,
            "item_name": i.item_name,
            "qty": i.qty,
            "notes": i.notes,
            "ordered_time": i.ordered_time,
            **status_block(i.status),
        })

    return {
        "station": {"name": st.name, "description": st.description, "group_items_by_order": grouped},
        "server_time": now_datetime(),
        "tickets": sorted(tickets.values(), key=lambda t: str(t["ordered_time"] or "")),
    }


@frappe.whitelist()
def advance(station, identifier):
    """
    Move an item (or, for stations that group by order, a whole order) to
    the next status of the station's flow. `identifier` is the Order Entry
    Item identifier, or the Table Order name for grouped stations.
    """
    st = _station(station)
    grouped = cint(st.group_items_by_order)
    filters = st.get_command_filters()

    if grouped:
        if identifier not in (filters.get("parent") or ("in", []))[1]:
            frappe.throw(_("Order {0} is not in this station's queue").format(identifier))
        current = frappe.db.get_value("Table Order", identifier, "status")
        new_status = st.next_status(current)
        frappe.db.set_value("Table Order", identifier, "status", new_status)
        order_name = identifier
    else:
        row = frappe.get_all(
            "Order Entry Item",
            filters={**filters, "identifier": identifier},
            fields=["name", "status", "parent"],
            limit=1,
        )
        if not row:
            frappe.throw(_("Item is not in this station's queue"))
        current = row[0].status
        new_status = st.next_status(current)
        frappe.db.set_value("Order Entry Item", row[0].name, "status", new_status)
        order_name = row[0].parent

    table = frappe.db.get_value("Table Order", order_name, "table")
    payload = {
        "station": st.name,
        "identifier": identifier,
        "order": order_name,
        "table": table,
        "status": new_status,
        "previous_status": current,
        "client_id": frappe.form_dict.get("client_id"),
    }
    frappe.publish_realtime("kitchen_update", payload, room=_ORDER_ROOM, after_commit=True)
    # waiters' order screens refresh the item status
    frappe.publish_realtime(
        "order_update",
        {**payload, "action": "update", "source": frappe.session.user},
        room=_ORDER_ROOM,
        after_commit=True,
    )
    return {"identifier": identifier, "status": new_status, "previous_status": current}
