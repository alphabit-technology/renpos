# renpos/api/voids.py
#
# Voids of items already sent to the kitchen (or of whole orders that have
# them) need a reason and leave a Ren Void Log row: who, what, why,
# and in which kitchen status. Pending items can be removed freely.

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

from renpos.api.guards import require_restaurant_user
from renpos.api.modifiers import summary as modifiers_summary

DEFAULT_REASONS = [
	("Customer changed mind", 0),
	("Wrong item entered", 0),
	("Kitchen error", 0),
	("Long wait", 0),
	("Quality complaint", 0),
	("Other", 1),
]


@frappe.whitelist()
def get_void_reasons():
	require_restaurant_user()
	return frappe.get_all(
		"Ren Void Reason",
		filters={"enabled": 1},
		fields=["name", "reason", "requires_note"],
		order_by="creation asc",
	)


def check_reason(reason, note=None):
	"""Validate a void reason sent by the client; returns (reason, note)."""
	if not reason:
		frappe.throw(_("Choose a reason to void items already sent to the kitchen"), title=_("Reason required"))
	row = frappe.db.get_value("Ren Void Reason", reason, ["name", "enabled", "requires_note"], as_dict=True)
	if not row or not row.enabled:
		frappe.throw(_("Void reason {0} is not valid").format(frappe.bold(reason)))
	note = (note or "").strip()
	if row.requires_note and not note:
		frappe.throw(_("Add a note for reason {0}").format(frappe.bold(reason)), title=_("Note required"))
	return row.name, note


def log(order, row, reason, note, void_type="Item"):
	frappe.get_doc({
		"doctype": "Ren Void Log",
		"voided_at": now_datetime(),
		"void_type": void_type,
		"reason": reason,
		"note": note,
		"voided_by": frappe.session.user,
		"order_name": order.name,
		"table": order.table,
		"pos_profile": order.get("pos_profile"),
		"ordered_by": order.owner,
		"item_code": row.item_code,
		"item_name": row.item_name,
		"modifiers": modifiers_summary(row.get("modifiers"))[:140] or None,
		"qty": flt(row.qty),
		"amount": flt(row.amount),
		"status_at_void": row.status,
	}).insert(ignore_permissions=True)


def install_default_reasons():
	if frappe.db.count("Ren Void Reason"):
		return
	for reason, requires_note in DEFAULT_REASONS:
		frappe.get_doc({
			"doctype": "Ren Void Reason",
			"reason": reason,
			"enabled": 1,
			"requires_note": cint(requires_note),
		}).insert(ignore_permissions=True)
