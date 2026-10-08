# -*- coding: utf-8 -*-
# renpos/api/parts.py
#
# Combos whose components are prepared at different production centers.
#
# An item with "Send components to their stations" (ren_route_components, on
# the item or its template) splits, for the kitchen only, into its parts:
# every component chosen that is a menu item (is_sales_item: the burger,
# the fries, the drink) goes to the center of its own item group. The
# order, its price, the invoice and the stock stay one line; the parts
# exist in the kitchen screens, the kitchen tickets and the status log.
#
#   Ren Order Item.ren_parts        [{option, item, item_group, label, qty, texts}]
#                                    set when the line is saved
#   Ren Order Item.ren_part_status  {option: status} once a part moved;
#                                    a part without one has the line's status
#
# A part's identifier at the kitchen is "<line identifier>~<option>". When a
# part moves, the line takes the status of its least advanced part, so the
# waiter sees the combo "Sent" until every part is done, and a center that
# handles the combo as a whole (an expo) gets it when the last part is ready.

import json

import frappe
from frappe.model.document import Document
from frappe.utils import cint, flt
from frappe.utils.caching import request_cache

SEP = "~"


def routes(item_code):
	"""The item (or its template) sends its components to their stations."""
	if not frappe.get_meta("Item").has_field("ren_route_components"):
		return False
	row = frappe.get_cached_value("Item", item_code, ["ren_route_components", "variant_of"], as_dict=True)
	if not row:
		return False
	if cint(row.ren_route_components):
		return True
	return bool(row.variant_of and cint(frappe.get_cached_value("Item", row.variant_of, "ren_route_components")))


def parts_of(item_code, modifiers):
	"""The parts of a line, or None when it isn't split."""
	if not routes(item_code):
		return None
	from renpos.api.modifiers import entry_text, parse
	mods = parse(modifiers)
	out = []
	for m in mods:
		if m.get("parent") or not m.get("item") or m.get("removed"):
			continue
		meta = frappe.get_cached_value("Item", m["item"], ["is_sales_item", "item_group"], as_dict=True)
		if not meta or not cint(meta.is_sales_item):
			continue  # an ingredient: it stays a note of the line
		kids = [k for k in mods if k.get("parent") == m.get("option")]
		size = next((k for k in kids if k.get("variant") and not k.get("removed")), None)
		label = m.get("label") or m["item"]
		if m.get("mode_text"):
			label = m["mode_text"].replace("{0}", label)
		if size:
			label = f"{label} {size['label']}"
		texts = [entry_text(k) for k in kids if not k.get("variant") and not k.get("swapped")]
		if m.get("instead_of"):
			texts.insert(0, frappe._("instead of {0}").format(m["instead_of"]))
		out.append({
			"option": m["option"],
			"item": size["item"] if size else m["item"],
			"item_group": meta.item_group,
			"label": label,
			"qty": cint(m.get("qty")) or 1,
			"texts": [t for t in texts if t],
		})
	return out or None


def _load(value):
	if not value:
		return None
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except ValueError:
			return None
	return value


def parts(row):
	return _load(row.get("ren_parts")) or []


def split(identifier):
	"""'<line>~<option>' -> (line identifier, option or None)"""
	base, _sep, option = (identifier or "").partition(SEP)
	return base, option or None


@request_cache
def status_rank():
	"""How far along each status is (the order the statuses were created: Pending, Sent, Processing...)."""
	names = frappe.get_all("Ren Order Status", order_by="creation asc, name asc", pluck="name")
	return {n: i for i, n in enumerate(names)}


def expand(row):
	"""The kitchen rows of a split line: one per part, with its own identifier and status."""
	statuses = _load(row.get("ren_part_status")) or {}
	out = []
	for p in parts(row):
		r = frappe._dict(row)
		r.update(
			identifier=f"{row.identifier}{SEP}{p['option']}",
			line_identifier=row.identifier,
			part=p["option"],
			item_code=p["item"],
			item_name=p["label"],
			item_group=p["item_group"],
			qty=flt(row.qty) * flt(p["qty"]),
			modifiers=json.dumps([{"text": t} for t in p["texts"]]),
			status=statuses.get(p["option"]) or row.status,
		)
		out.append(r)
	return out


def route(rows, handles, statuses=None):
	"""
	What a production center gets of some order lines: whole lines of its
	item groups, and the parts of split lines that are of its groups (a
	split line comes whole only to a center that has none of its parts).
	`handles(item_group)` says whether the center takes a group; `statuses`
	limits to the lines / parts in those statuses.
	"""
	ok = (lambda s: True) if statuses is None else (lambda s: s in statuses)
	out = []
	for r in rows:
		row = frappe._dict(r.as_dict() if isinstance(r, Document) else r)
		group = row.get("item_group") or frappe.get_cached_value("Item", row.item_code, "item_group")
		if parts(row):
			mine = [p for p in expand(row) if handles(p.item_group) and ok(p.status)]
			if not mine and handles(group) and ok(row.status):
				out.append(r)
			out += mine
		elif handles(group) and ok(row.status):
			out.append(r)
	return out


def set_part_status(line_name, option, from_status, to_status):
	"""
	Compare-and-set one part's status; the line takes the status of its
	least advanced part. Returns the line's status, or None if the part
	wasn't in from_status (another screen moved it).
	"""
	row = frappe.db.sql(
		"""SELECT status, ren_parts, ren_part_status FROM `tabRen Order Item` WHERE name = %s FOR UPDATE""",
		line_name, as_dict=True)
	if not row:
		return None
	row = row[0]
	statuses = _load(row.ren_part_status) or {}
	if (statuses.get(option) or row.status) != from_status:
		return None
	statuses[option] = to_status
	rank = status_rank()
	every = [statuses.get(p["option"]) or row.status for p in parts(row)] or [to_status]
	line_status = min(every, key=lambda s: rank.get(s, 10 ** 6))
	frappe.db.sql("""UPDATE `tabRen Order Item` SET ren_part_status = %s, status = %s WHERE name = %s""",
	              (json.dumps(statuses), line_status, line_name))
	return line_status


def current_status(identifier):
	"""Status of a line or of a part ('<line>~<option>')."""
	base, option = split(identifier)
	row = frappe.db.get_value("Ren Order Item", {"identifier": base, "parenttype": "Ren Order"},
	                          ["status", "ren_part_status"], as_dict=True)
	if not row:
		return None
	if not option:
		return row.status
	return (_load(row.ren_part_status) or {}).get(option) or row.status


@request_cache
def waiting_statuses():
	"""Statuses some production center works on (every step of a flow but the last)."""
	out = set()
	for name in frappe.get_all("Ren Station", pluck="name"):
		out.update(frappe.get_doc("Ren Station", name).flow[:-1])
	return tuple(sorted(out)) or ("__none__",)
