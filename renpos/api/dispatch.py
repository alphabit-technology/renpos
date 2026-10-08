# -*- coding: utf-8 -*-
# renpos/api/dispatch.py
#
# Dispatch / expo stations: a grouped Ren Station with "Wait for the whole
# order". It sees each order of its rooms / tables as soon as it is sent and
# follows it (tracking), but its button only works once every item reached
# the station's first status:
#
#   here     the line is in this station's flow (but its last status)
#   waiting  another station that handles its item group still works on it
#   orphan   no station handles it (a soda nobody prepares): it counts as
#            arrived, and moves with the order
#   (gone)   it left this station (its last status, or a Finished status)
#
# Statuses carry a meaning (Ren Order Status.kind): Ready (the kitchen is
# done) and Finished (it reached the guest). A status with "Ask who delivers"
# takes the driver: Ren Order.ren_driver / ren_driver_name, ren_dispatched_at.
# Reaching a Finished status sets ren_delivered_at. Nothing is charged here.

import frappe
from frappe import _
from frappe.utils import cint, get_fullname, now_datetime

from renpos.api.statuses import editable_statuses

ALL = "all"  # ticket key of a whole order: "<order>::all"


def status_meta(statuses=None):
	"""{status: {kind, ask_driver}}"""
	filters = {"name": ["in", list(statuses)]} if statuses else {}
	return {r.name: r for r in frappe.get_all("Ren Order Status", filters=filters,
	                                            fields=["name", "kind", "ask_driver"])}


def finished_statuses():
	return {r.name for r in frappe.get_all("Ren Order Status", filters={"kind": "Finished"}, fields=["name"])}


def _upstream(st):
	"""{item_group: statuses other stations still work on} (every step of their flow but the last)."""
	out = {}
	for name in frappe.get_all("Ren Station", filters={"name": ["!=", st.name]}, pluck="name"):
		other = frappe.get_cached_doc("Ren Station", name)
		steps = set(other.flow[:-1])
		for g in other._items_group:
			out.setdefault(g, set()).update(steps)
	return out


def order_lines(st, orders=None, for_update=False):
	"""
	The lines this station follows, each with `state` here / waiting / orphan
	(see the top). `orders` limits it to those orders.
	"""
	flow = st.flow
	working = set(flow[:-1])
	gone = {flow[-1]} | finished_statuses()
	groups = st._items_group
	if not groups:
		return []
	conditions = ["i.parenttype = 'Ren Order'", "i.qty > 0", "i.item_group IN %(groups)s",
	              "IFNULL(i.status, '') NOT IN %(skip)s", "IFNULL(o.status, '') NOT IN ('Cancelled', 'Invoiced')"]
	values = {"groups": groups, "skip": list(editable_statuses()) + list(gone) + [""]}
	where = st.origin_condition("o")
	if where:
		conditions.append(where[0])
		values.update(where[1])
	if orders:
		conditions.append("i.parent IN %(orders)s")
		values["orders"] = list(orders)
	rows = frappe.db.sql(f"""
		SELECT i.name, i.identifier, i.item_code, i.item_name, i.item_group, i.qty, i.notes, i.status,
		       i.parent, i.ordered_time, i.modifiers, i.idx,
		       o.table, o.table_description, o.room_description, o.dinners, o.owner AS order_owner,
		       o.notes AS order_notes, o.ren_delivery, o.ren_delivery_address, o.ren_deliver_by,
		       o.ren_driver, o.ren_driver_name
		FROM `tabRen Order Item` i JOIN `tabRen Order` o ON o.name = i.parent
		WHERE {" AND ".join(conditions)}
		ORDER BY i.ordered_time ASC, i.idx ASC
		{"FOR UPDATE" if for_update else ""}""", values, as_dict=True)
	upstream = _upstream(st)
	for r in rows:
		if r.status in working:
			r.state = "here"
		elif r.status in upstream.get(r.item_group, ()):
			r.state = "waiting"
		else:
			r.state = "orphan"
	# an order nothing of which reached this station yet, and that nobody works on, isn't shown
	return rows


def current_status(st, rows):
	"""The ticket's status: the earliest among the lines that arrived (orphans count as the first)."""
	order_of = {s: i for i, s in enumerate(st.flow)}
	arrived = [r.status if r.state == "here" else st.flow[0] for r in rows if r.state != "waiting"]
	return min(arrived, key=lambda s: order_of.get(s, 0)) if arrived else st.flow[0]


def tickets(st, status_block, modifier_texts, rounds=None):
	"""The station's whole-order tickets (one per order), oldest first."""
	by_order = {}
	for r in order_lines(st):
		by_order.setdefault(r.parent, []).append(r)
	out = []
	for order, rows in by_order.items():
		first = rows[0]
		waiting = [r for r in rows if r.state == "waiting"]
		status = current_status(st, rows)
		t = {
			"key": f"{order}::{ALL}",
			"order": order,
			"short_name": order[-5:],
			"round": 1,
			"whole_order": 1,
			"table": first.table,
			"table_description": first.table_description or first.table,
			"room_description": first.room_description,
			"dinners": first.dinners,
			"notes": first.order_notes,
			"server": get_fullname(first.order_owner) if first.order_owner else None,
			"ordered_time": min(str(r.ordered_time or "") for r in rows),
			"delivery": cint(first.ren_delivery),
			"address": first.ren_delivery_address or "",
			"deliver_by": str(first.ren_deliver_by or ""),
			"driver": first.ren_driver_name or (get_fullname(first.ren_driver) if first.ren_driver else ""),
			"total_items": len(rows),
			"waiting_items": len(waiting),
			"ready": not waiting,
			"items": [],
			**status_block(status),
		}
		if waiting:
			t["next_status"] = None  # tracking only, until everything arrives
			t["action"] = None
		for r in rows:
			t["items"].append({
				"identifier": r.identifier,
				"item_code": r.item_code,
				"item_name": r.item_name,
				"qty": r.qty,
				"notes": r.notes,
				"modifiers": modifier_texts(r.modifiers),
				"ordered_time": r.ordered_time,
				"waiting": r.state == "waiting",
				**status_block(r.status if r.state == "here" else (r.status if r.state == "waiting" else st.flow[0])),
			})
		out.append(t)
	return sorted(out, key=lambda t: t["ordered_time"])


def rows_to_advance(st, order, expected=None):
	"""
	The lines a whole-order ticket moves: those at the ticket's status (and the
	orphans, when it is the first one). Refuses while something is still cooking.
	"""
	from renpos.api.kitchen import KitchenConflict
	rows = order_lines(st, orders=[order], for_update=True)
	if not rows:
		frappe.throw(_("This order is no longer waiting here; the screen will refresh"), KitchenConflict)
	waiting = [r for r in rows if r.state == "waiting"]
	if waiting:
		frappe.throw(_("Not everything is ready: {0} still in preparation").format(
			", ".join(sorted({r.item_name for r in waiting}))), title=_("Wait for the kitchen"))
	current = current_status(st, rows)
	if expected and current != expected:
		frappe.throw(_("Another screen already moved it to {0}; the screen will refresh").format(_(current)),
		             KitchenConflict)
	here = [r for r in rows if r.state == "here" and r.status == current]
	orphans = [r for r in rows if r.state == "orphan"] if current == st.flow[0] else []
	return current, here, orphans


def move_orphans(rows, to_status):
	"""Orphans move from wherever they are (compare-and-set on their own status)."""
	for r in rows:
		frappe.db.sql("UPDATE `tabRen Order Item` SET status = %s WHERE name = %s AND status = %s",
		              (to_status, r.name, r.status))


# ─────────────────────────────────────────────
# Drivers
# ─────────────────────────────────────────────

def needs_driver(status):
	return bool(status) and cint(frappe.db.get_value("Ren Order Status", status, "ask_driver"))


@frappe.whitelist()
def drivers(station):
	"""People who deliver for the station's restaurant: their role has "Delivers orders"."""
	from renpos.api.kitchen import _station
	st = _station(station)
	restaurant = frappe.db.get_value("Ren Floor", st.floor, "restaurant") if st.floor else None
	roles = frappe.get_all("Ren Role", filters={"delivers_orders": 1}, pluck="name")
	rows = frappe.get_all("Ren Staff", filters={"restaurant": restaurant, "enabled": 1,
	                                            "restaurant_role": ["in", roles or [""]]}, pluck="user") \
		if restaurant else []
	out = [{"user": u, "full_name": get_fullname(u)} for u in sorted(set(rows))]
	return sorted(out, key=lambda d: d["full_name"])


def set_driver(orders, driver=None, driver_name=None):
	"""The driver of the orders moving into an "Ask who delivers" status (a staff user or a name)."""
	driver = (driver or "").strip() or None
	driver_name = (driver_name or "").strip()[:80]
	if driver and not frappe.db.exists("User", driver):
		frappe.throw(_("Driver {0} not found").format(driver))
	if not driver and not driver_name:
		frappe.throw(_("Choose who delivers it"), title=_("Driver"))
	for order in orders:
		frappe.db.set_value("Ren Order", order, {
			"ren_driver": driver, "ren_driver_name": driver_name or (get_fullname(driver) if driver else ""),
			"ren_dispatched_at": now_datetime(),
		}, update_modified=False)


def mark_finished(orders, status):
	"""Every line of the order reached a Finished status: note when it was delivered."""
	if status not in finished_statuses():
		return
	for order in orders:
		left = frappe.db.sql("""SELECT COUNT(*) FROM `tabRen Order Item` WHERE parent = %s AND parenttype = 'Ren Order'
			AND qty > 0 AND IFNULL(status, '') NOT IN %s""", (order, list(finished_statuses())))[0][0]
		if not left:
			frappe.db.set_value("Ren Order", order, "ren_delivered_at", now_datetime(), update_modified=False)
