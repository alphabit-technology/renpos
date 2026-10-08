# renpos/api/register.py
#
# Cash register (shift) for the current cashier, on top of ERPNext's
# POS Opening Entry / POS Closing Entry:
#
#   get_register(pos_profile)        status + live shift report (X report)
#   open_register(pos_profile, ...)  opening float per mode of payment
#   close_register(pos_profile, ...) counted amounts -> POS Closing Entry (Z report)
#
# Each cashier has their own register (see invoicing.get_open_opening_entry).

import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, nowdate

from renpos.api.guards import check_billing_profile, check_pos_profile_access, require_restaurant_user
from renpos.api.invoicing import (
	_as_administrator,
	can_take_payments,
	get_open_opening_entry,
	open_entries,
	opening_status,
	payment_modes,
)


def _require_cashier(pos_profile):
	require_restaurant_user()
	check_billing_profile(pos_profile)
	if not can_take_payments():
		raise frappe.PermissionError(_("You are not allowed to take payments (cashier roles are missing)"))


def _parse(value):
	if isinstance(value, str):
		value = json.loads(value or "[]")
	return value or []


def _shift_report(opening):
	"""Totals of the shift so far: invoices, payments per mode, taxes, voids."""
	from erpnext.accounts.doctype.pos_closing_entry.pos_closing_entry import get_invoices

	end = now_datetime()
	# ERPNext checks broad read rights on invoices; the cashier's own shift
	# is always theirs to see.
	with _as_administrator():
		data = get_invoices(opening.period_start_date, end, opening.pos_profile, opening.user)

	invoices = data.get("invoices") or []
	opening_by_mode = {d.mode_of_payment: flt(d.opening_amount) for d in opening.balance_details}
	paid_by_mode = {p.mode_of_payment: flt(p.amount) for p in data.get("payments") or []}
	modes = list(dict.fromkeys(list(opening_by_mode) + list(paid_by_mode)))

	voids = frappe.db.sql(
		"""SELECT COUNT(*) AS count, SUM(amount) AS amount FROM `tabRen Void Log`
		WHERE pos_profile = %s AND voided_at >= %s""",
		(opening.pos_profile, opening.period_start_date),
		as_dict=True,
	)[0]

	return {
		"from": opening.period_start_date,
		"to": end,
		"invoices": len(invoices),
		"returns": sum(1 for i in invoices if i.get("is_return")),
		"grand_total": flt(sum(flt(i.grand_total) for i in invoices), 2),
		"net_total": flt(sum(flt(i.net_total) for i in invoices), 2),
		"taxes": flt(sum(flt(i.total_taxes_and_charges) for i in invoices), 2),
		"tax_breakdown": [{"account": t.account_head, "amount": flt(t.tax_amount)} for t in data.get("taxes") or []],
		"payments": [
			{
				"mode_of_payment": m,
				"opening": opening_by_mode.get(m, 0),
				"sales": paid_by_mode.get(m, 0),
				"expected": flt(opening_by_mode.get(m, 0) + paid_by_mode.get(m, 0), 2),
			}
			for m in modes
		],
		"voids": {"count": (voids or {}).get("count") or 0, "amount": flt((voids or {}).get("amount"))},
	}


def _entry_info(entry):
	return {"name": entry.name, "user": entry.user, "pos_profile": entry.pos_profile,
	        "user_name": frappe.utils.get_fullname(entry.user), "period_start_date": entry.period_start_date}


def _blocker(pos_profile):
	"""
	Why the cashier can't open this register (ERPNext v16: one open register per
	POS Profile, and per user): someone else's open shift on this profile
	(status "taken"; a manager can close it here), or the cashier's own open
	shift on another profile (status "elsewhere").
	"""
	user = frappe.session.user
	other = [e for e in open_entries(pos_profile=pos_profile) if e.user != user]
	if other:
		from renpos.api import access
		from renpos.api.guards import is_manager
		entry = other[0]
		out = {"status": "taken", "opening": _entry_info(entry),
		       "can_close": bool(is_manager() and access.can("manage_register", pos_profile))}
		if out["can_close"]:
			out["report"] = _shift_report(frappe.get_doc("POS Opening Entry", entry.name))
		return out
	mine = [e for e in open_entries(user=user) if e.pos_profile != pos_profile]
	if mine:
		return {"status": "elsewhere", "opening": _entry_info(mine[0])}
	return None


def _blocker_message(b):
	o = b["opening"]
	since = frappe.format_value(o["period_start_date"], {"fieldtype": "Datetime"})
	if b["status"] == "taken":
		return _("The register of {0} is already open by {1} since {2}. Only one register per POS Profile can be open: "
		         "{1} (or a manager) has to close it first, or use another POS Profile.").format(
			frappe.bold(o["pos_profile"]), frappe.bold(o["user_name"]), since)
	return _("Your register of {0} is open since {1}. Close it before opening {2}.").format(
		frappe.bold(o["pos_profile"]), since, frappe.bold(frappe.form_dict.get("pos_profile") or ""))


@frappe.whitelist()
def get_register(pos_profile):
	"""
	{status: open|closed|outdated|no_permission, opening, report, modes}
	"""
	require_restaurant_user()
	check_pos_profile_access(pos_profile)
	profile = frappe.get_cached_doc("POS Profile", pos_profile)
	modes = payment_modes(profile)
	try:
		check_billing_profile(pos_profile)
	except frappe.PermissionError:
		return {"status": "no_permission", "modes": modes}
	if not can_take_payments():
		return {"status": "no_permission", "modes": modes}
	printer = profile.get("ren_receipt_printer")

	opening, problem = opening_status(pos_profile)
	if not opening:
		blocker = _blocker(pos_profile)
		if blocker:
			return {**blocker, "modes": modes}
		return {"status": "closed", "modes": modes}

	opening_doc = frappe.get_doc("POS Opening Entry", opening.name)
	return {
		"status": problem or "open",
		"opening": {"name": opening_doc.name, "period_start_date": opening_doc.period_start_date, "user": opening_doc.user},
		"report": _shift_report(opening_doc),
		"modes": modes,
		"receipt_printer": printer,
	}


@frappe.whitelist()
def open_register(pos_profile, balances=None):
	"""balances: [{mode_of_payment, opening_amount}] (the float in the drawer)."""
	_require_cashier(pos_profile)
	from renpos.api import access
	access.require("manage_register", pos_profile)
	# serialize opens of this profile so a double tap can't open two registers
	frappe.db.get_value("POS Profile", pos_profile, "name", for_update=True)
	if get_open_opening_entry(pos_profile):
		frappe.throw(_("Your cash register is already open"), title=_("Register open"))
	blocker = _blocker(pos_profile)
	if blocker:
		frappe.throw(_blocker_message(blocker), title=_("Register in use"))

	profile = frappe.get_cached_doc("POS Profile", pos_profile)
	allowed = {m["mode_of_payment"] for m in payment_modes(profile)}
	amounts = {}
	for b in _parse(balances):
		mode = b.get("mode_of_payment")
		if mode not in allowed:
			frappe.throw(_("Mode of payment {0} is not enabled in POS Profile {1}").format(mode, pos_profile))
		amount = flt(b.get("opening_amount"))
		if amount < 0:
			frappe.throw(_("Opening amounts can't be negative"))
		amounts[mode] = amount

	doc = frappe.get_doc({
		"doctype": "POS Opening Entry",
		"user": frappe.session.user,
		"pos_profile": pos_profile,
		"company": profile.company,
		"period_start_date": now_datetime(),
		"posting_date": nowdate(),
		# every mode appears, so the closing shows all of them
		"balance_details": [{"mode_of_payment": m, "opening_amount": amounts.get(m, 0)} for m in
		                    [x["mode_of_payment"] for x in payment_modes(profile)]],
	})
	# can_take_payments() checked the cashier roles; POS Opening Entry rights
	# are commonly given only to Accounts Manager.
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	return get_register(pos_profile)


@frappe.whitelist()
def close_register(pos_profile, counted=None, preview=0, opening=None):
	"""
	counted: [{mode_of_payment, closing_amount}] as counted by the cashier.
	With preview=1 only returns what the closing would look like.
	opening: a manager closes someone else's open shift of this POS Profile.
	"""
	_require_cashier(pos_profile)
	from renpos.api import access
	access.require("manage_register", pos_profile)
	if opening:
		from renpos.api.guards import is_manager
		entry = next((e for e in open_entries(pos_profile=pos_profile) if e.name == opening), None)
		if not entry:
			frappe.throw(_("That register isn't open anymore"))
		if entry.user != frappe.session.user and not is_manager():
			raise frappe.PermissionError(_("Only a manager can close someone else's register"))
		opening = entry
	else:
		opening = get_open_opening_entry(pos_profile)
	if not opening:
		frappe.throw(_("Your cash register is not open"))
	opening_doc = frappe.get_doc("POS Opening Entry", opening.name)

	from erpnext.accounts.doctype.pos_closing_entry.pos_closing_entry import make_closing_entry_from_opening

	with _as_administrator():
		closing = make_closing_entry_from_opening(opening_doc)

	counted_by_mode = {c.get("mode_of_payment"): flt(c.get("closing_amount")) for c in _parse(counted)}
	opening_by_mode = {d.mode_of_payment: flt(d.opening_amount) for d in opening_doc.balance_details}

	rows = {r.mode_of_payment: r for r in closing.payment_reconciliation}
	for mode, amount in opening_by_mode.items():
		if mode not in rows:
			rows[mode] = closing.append("payment_reconciliation", {"mode_of_payment": mode, "expected_amount": 0})
	for mode, row in rows.items():
		row.opening_amount = opening_by_mode.get(mode, 0)
		# ERPNext's helper leaves the opening float out of "expected"
		row.expected_amount = flt(flt(row.expected_amount) + row.opening_amount, 2)
		row.closing_amount = counted_by_mode.get(mode, row.expected_amount if preview else 0)
		row.difference = flt(row.closing_amount - row.expected_amount, 2)

	summary = {
		"report": _shift_report(opening_doc),
		"reconciliation": [
			{
				"mode_of_payment": r.mode_of_payment,
				"opening": flt(r.opening_amount),
				"expected": flt(r.expected_amount),
				"counted": flt(r.closing_amount),
				"difference": flt(r.difference),
			}
			for r in closing.payment_reconciliation
		],
	}
	if frappe.utils.cint(preview):
		return summary

	missing = [m for m in rows if m not in counted_by_mode]
	if missing:
		frappe.throw(_("Enter the counted amount for: {0}").format(", ".join(missing)), title=_("Count missing"))

	closing.flags.ignore_permissions = True
	closing.insert()
	closing.submit()
	summary["closing_entry"] = closing.name
	# the recipes' ingredients of the shift's paid orders leave stock now (never blocks the close)
	from renpos.api.recipes import post_usage
	with _as_administrator():
		summary["ingredients_entry"] = post_usage(pos_profile)
	summary["status"] = frappe.db.get_value("POS Closing Entry", closing.name, "status")
	return summary
