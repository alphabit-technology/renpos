# renpos/api/printing.py
#
# Direct printing to thermal printers (ESC/POS over the network, port 9100).
#
#   Ren Printer      host/port, paper width, cut, copies
#   Ren Station.printer     kitchen tickets for the items that station prepares
#   POS Profile (Restaurant tab)
#       ren_receipt_printer            bills, receipts, cash drawer
#       ren_print_kitchen_tickets      tickets when an order is sent
#       ren_print_receipt_on_payment   receipt after charging
#       ren_open_drawer_on_cash        kick the drawer when cash is taken
#
# Every print is a Ren Print Job (Queued -> Printed | Failed) sent by
# a background worker, so a printer that is off never blocks the waiter; a
# failed job can be sent again. The server must be able to reach the
# printers (same network / VPN).

import base64
import socket
import textwrap

import frappe
from frappe import _
from frappe.utils import cint, flt, format_datetime, now_datetime

from renpos.api.guards import (
	check_pos_profile_access,
	get_order,
	profile_restaurant,
	require_restaurant_user,
)
from renpos.api.modifiers import texts as modifier_texts

try:
	from frappe.realtime import get_doctype_room
	_ORDER_ROOM = get_doctype_room("Ren Order")
except ImportError:
	_ORDER_ROOM = "doctype:Ren Order"

ESC = b"\x1b"
GS = b"\x1d"
CONNECT_TIMEOUT = 5


# ─────────────────────────────────────────────
# ESC/POS ticket builder
# ─────────────────────────────────────────────

class Ticket:
	"""Builds ESC/POS bytes and a plain-text preview at the same time."""

	def __init__(self, width=48):
		self.width = width
		self.out = bytearray(ESC + b"@" + ESC + b"t\x10")  # init, code page WPC1252
		self.preview = []

	def _text(self, s):
		return (s or "").encode("cp1252", errors="replace")

	def _style(self, bold=False, size=1, align="left"):
		self.out += ESC + b"a" + bytes([{"left": 0, "center": 1, "right": 2}[align]])
		self.out += ESC + b"E" + bytes([1 if bold else 0])
		self.out += GS + b"!" + bytes([{1: 0x00, 2: 0x11, "h": 0x01}[size]])

	def line(self, text="", bold=False, size=1, align="left"):
		# double width halves the characters that fit
		cols = self.width // 2 if size == 2 else self.width
		for chunk in (textwrap.wrap(text, cols) or [""]):
			self._style(bold, size, align)
			self.out += self._text(chunk) + b"\n"
			pad = {"center": (cols - len(chunk)) // 2, "right": cols - len(chunk)}.get(align, 0)
			self.preview.append(" " * max(pad, 0) + chunk)
		self._style()
		return self

	def cols(self, left, right, bold=False, size=1):
		"""left text + right-aligned text on one line (wraps the left side)."""
		cols = self.width // 2 if size == 2 else self.width
		room = max(cols - len(right) - 1, 8)
		parts = textwrap.wrap(left, room) or [""]
		for i, part in enumerate(parts):
			tail = right if i == len(parts) - 1 else ""
			self.line(part.ljust(cols - len(tail)) + tail if tail else part, bold=bold, size=size)
		return self

	def rule(self, char="-"):
		return self.line(char * self.width)

	def feed(self, n=1):
		self.out += ESC + b"d" + bytes([n])
		self.preview.extend([""] * n)
		return self

	def beep(self):
		self.out += ESC + b"B\x03\x02"  # 3 beeps (printers without buzzer ignore it)
		return self

	def drawer(self):
		self.out += ESC + b"p\x00\x19\xfa"  # pulse drawer pin 2
		self.preview.append("[open drawer]")
		return self

	def cut(self):
		self.feed(4)
		self.out += GS + b"V\x42\x00"  # feed and partial cut
		self.preview.append("[cut]")
		return self

	def bytes(self):
		return bytes(self.out)

	def text(self):
		return "\n".join(self.preview)


def _printer(name):
	p = frappe.get_cached_doc("Ren Printer", name)
	width = cint(p.characters_per_line) or (32 if p.paper_width == "58 mm" else 48)
	return p, width


def _money(value, currency=None):
	return frappe.format_value(flt(value), {"fieldtype": "Currency", "options": currency}) if currency \
		else f"{flt(value):,.2f}"


# ─────────────────────────────────────────────
# Jobs
# ─────────────────────────────────────────────

def queue_job(printer, job_type, ticket, reference_doctype=None, reference_name=None):
	p, _w = _printer(printer)
	if not p.enabled:
		return None
	if p.cut_paper and job_type != "Drawer":
		ticket.cut()
	payload = ticket.bytes() * max(cint(p.copies), 1) if job_type in ("Kitchen", "Receipt", "Bill") else ticket.bytes()
	job = frappe.get_doc({
		"doctype": "Ren Print Job",
		"printer": printer,
		"job_type": job_type,
		"status": "Queued",
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
		"preview": ticket.text(),
		"payload": base64.b64encode(payload).decode(),
	}).insert(ignore_permissions=True)

	if frappe.flags.in_test or frappe.flags.ren_print_now:
		send_job(job.name)
	else:
		frappe.enqueue(
			"renpos.api.printing.send_job",
			queue="short", job=job.name, enqueue_after_commit=True,
		)
	return job.name


def send_job(job):
	"""Background: push the job's bytes to the printer."""
	doc = frappe.get_doc("Ren Print Job", job)
	printer = frappe.get_doc("Ren Printer", doc.printer)
	data = base64.b64decode(doc.payload or "")
	error = None
	try:
		with socket.create_connection((printer.host, cint(printer.port) or 9100), timeout=CONNECT_TIMEOUT) as s:
			s.sendall(data)
	except OSError as e:
		error = f"{printer.host}:{printer.port} — {e}"

	doc.db_set({
		"status": "Failed" if error else "Printed",
		"error": error,
		"attempts": cint(doc.attempts) + 1,
		"printed_at": None if error else now_datetime(),
	}, update_modified=False)
	frappe.publish_realtime(
		"restaurant_print",
		{"job": doc.name, "printer": doc.printer, "type": doc.job_type, "status": doc.status, "error": error,
		 "reference": doc.reference_name, "owner": doc.owner},
		room=_ORDER_ROOM,
		after_commit=not frappe.flags.in_test,
	)
	return doc.status


@frappe.whitelist()
def retry_job(job):
	require_restaurant_user()
	doc = frappe.get_doc("Ren Print Job", job)
	# only jobs of the user's POS Profile, and reprinting is a role action
	from renpos.api import access
	profile = None
	if doc.reference_doctype == "Ren Order" and doc.reference_name:
		profile = frappe.db.get_value("Ren Order", doc.reference_name, "pos_profile")
	elif doc.reference_doctype == "POS Profile":
		profile = doc.reference_name
	elif doc.reference_doctype in ("POS Invoice", "Sales Invoice") and doc.reference_name:
		profile = frappe.db.get_value(doc.reference_doctype, doc.reference_name, "pos_profile")
	if profile:
		check_pos_profile_access(profile)
	if doc.status != "Failed":
		access.require("reprint", profile, reference=(doc.reference_doctype, doc.reference_name) if doc.reference_name else None)
	if doc.job_type == "Drawer":
		# opening the drawer again is a cashier action (see open_drawer)
		from renpos.api.invoicing import can_take_payments
		if not can_take_payments() or doc.status != "Failed":
			raise frappe.PermissionError(_("Only cashiers can open the cash drawer"))
	elif doc.status != "Failed" and doc.job_type not in ("Kitchen", "Bill", "Receipt"):
		frappe.throw(_("Only failed print jobs can be sent again"))
	# failed jobs are sent again; printed tickets too (a copy)
	doc.db_set("status", "Queued")
	if frappe.flags.in_test:
		return send_job(doc.name)
	frappe.enqueue("renpos.api.printing.send_job", queue="short", job=doc.name,
	               enqueue_after_commit=True)
	return "Queued"


def print_test_page(printer):
	if not frappe.has_permission("Ren Printer", "write"):
		raise frappe.PermissionError
	p, width = _printer(printer)
	t = Ticket(width)
	t.line(_("Test page"), bold=True, size=2, align="center")
	t.line(p.printer_name, align="center").line(f"{p.host}:{p.port} · {width} col", align="center")
	t.rule().line("0123456789" * (width // 10)).line("ÁÉÍÓÚ ñ € $ ¿?").rule()
	t.line(format_datetime(now_datetime()), align="center")
	return queue_job(printer, "Test", t)


# ─────────────────────────────────────────────
# Kitchen tickets
# ─────────────────────────────────────────────

def _station_handles(station, order, item_group, groups_cache):
	if station.name not in groups_cache:
		groups_cache[station.name] = set(station._items_group)
	if item_group not in groups_cache[station.name]:
		return False
	return station.takes_order_from(order.get("room"), order.get("table"))


def _stations_with_printer(order):
	restaurant = order.get("restaurant") or profile_restaurant(order.pos_profile)
	rows = frappe.db.sql(
		"""SELECT s.name FROM `tabRen Station` s
		LEFT JOIN `tabRen Floor` f ON f.name = s.floor
		WHERE IFNULL(s.printer, '') != '' AND (%(r)s IS NULL OR f.restaurant = %(r)s)""",
		{"r": restaurant},
	)
	return [frappe.get_doc("Ren Station", r[0]) for r in rows]


def kitchen_ticket(order, rows, station_title, width, beep=False, reprint=False, void_reason=None, fire=False):
	t = Ticket(width)
	if beep:
		t.beep()
	if fire:
		t.line(f"*** {_('FIRE')} ***", bold=True, size=2, align="center")
	if reprint:
		t.line(_("REPRINT"), bold=True, align="center")
	if void_reason:
		t.line(f"*** {_('VOID')} ***", bold=True, size=2, align="center")
		t.line(void_reason, bold=True, align="center")
	t.line(station_title, bold=True, size=2, align="center")
	t.line(f"{order.table_description or order.table} · {order.room_description or ''}".strip(" ·"),
	       bold=True, align="center")
	server = frappe.utils.get_fullname(order.owner) if order.owner else ""
	t.line(f"{_('Order')} {order.name[-5:]} · {server}", align="center")
	t.line(format_datetime(now_datetime(), "HH:mm") + (f" · {_('Guests')}: {order.dinners}" if order.get("dinners") else ""),
	       align="center")
	t.rule("=")
	for r in rows:
		t.line(f"{flt(r.qty):g} x {r.item_name}", bold=True, size="h")
		for text in modifier_texts(r.get("modifiers")):
			t.line(f"   > {text}", bold=text.startswith(_("NO ")))
		if r.notes:
			t.line(f"   ! {r.notes}", bold=True)
	t.rule("=")
	if order.get("notes"):
		t.line(order.notes, bold=True)
	return t


def route(rows, handles, statuses=None):
	from renpos.api.parts import route as route_parts
	return route_parts(rows, handles, statuses)


def print_kitchen_tickets(order, rows, fire=False):
	"""Called by send_order with the rows just sent. Returns the job names."""
	if not rows or not cint(frappe.get_cached_value("POS Profile", order.pos_profile, "ren_print_kitchen_tickets")):
		return []
	jobs, cache = [], {}
	for station in _stations_with_printer(order):
		# a combo split into parts prints each part at its own center (api/parts.py)
		mine = route(rows, lambda g: _station_handles(station, order, g, cache))
		if not mine:
			continue
		p, width = _printer(station.printer)
		title = (station.description or station.name).strip()
		ticket = kitchen_ticket(order, mine, title, width, beep=cint(p.beep), fire=fire)
		job = queue_job(station.printer, "Kitchen", ticket, "Ren Order", order.name)
		if job:
			jobs.append(job)
	return jobs


def print_void_tickets(order, rows, reason=None, note=None):
	"""
	Voided lines that were already at a production center: a VOID ticket on
	that center's printer, so the cook stops making them. Called before the
	lines are removed; returns the job names.
	"""
	if not rows or not cint(frappe.get_cached_value("POS Profile", order.pos_profile, "ren_print_kitchen_tickets")):
		return []
	jobs, cache = [], {}
	why = " · ".join(x for x in (reason, note) if x)
	for station in _stations_with_printer(order):
		waiting = set(station.working_statuses)
		mine = route(rows, lambda g: _station_handles(station, order, g, cache), waiting)
		if not mine:
			continue
		p, width = _printer(station.printer)
		title = (station.description or station.name).strip()
		ticket = kitchen_ticket(order, mine, title, width, beep=cint(p.beep), void_reason=why or _("Voided"))
		job = queue_job(station.printer, "Kitchen", ticket, "Ren Order", order.name)
		if job:
			jobs.append(job)
	return jobs


# ─────────────────────────────────────────────
# Bill (pre-check) and receipt
# ─────────────────────────────────────────────

def _header(t, company, order=None, inv=None):
	t.line(frappe.get_cached_value("Company", company, "company_name") or company, bold=True, size=2, align="center")
	addr = frappe.db.get_value("Dynamic Link", {"link_doctype": "Company", "link_name": company,
	                                             "parenttype": "Address"}, "parent")
	if addr:
		a = frappe.db.get_value("Address", addr, ["address_line1", "city", "phone"], as_dict=True) or {}
		for part in (a.get("address_line1"), a.get("city"), a.get("phone")):
			if part:
				t.line(part, align="center")
	t.rule()
	if order:
		t.cols(f"{_('Table')} {order.table_description or order.table}", order.name[-5:])
		if order.owner:
			t.line(f"{_('Server')}: {frappe.utils.get_fullname(order.owner)}")
	if inv:
		t.cols(f"{_('Invoice')} {inv.name}", format_datetime(now_datetime(), "MM/dd/yy HH:mm"))
	t.rule()


def _items(t, inv, currency):
	for row in inv.items:
		t.cols(f"{flt(row.qty):g} {row.item_name}", _money(row.amount, currency))
		if row.description and "<small>" in (row.description or ""):
			t.line("   " + frappe.utils.strip_html(row.description.split("<small>", 1)[1]))
	t.rule()
	t.cols(_("Subtotal"), _money(inv.net_total, currency))
	for tax in inv.taxes or []:
		t.cols(tax.description or tax.account_head, _money(tax.tax_amount, currency))
	if flt(inv.discount_amount):
		t.cols(_("Discount"), "-" + _money(inv.discount_amount, currency))
	t.cols(_("TOTAL"), _money(inv.rounded_total or inv.grand_total, currency), bold=True, size=2)


def bill_ticket(order, width):
	from renpos.api.invoicing import build_invoice_preview, tip_settings

	inv = build_invoice_preview(order)
	profile = frappe.get_cached_doc("POS Profile", order.pos_profile)
	t = Ticket(width)
	_header(t, inv.company, order=order)
	_items(t, inv, inv.currency)
	tips = tip_settings(profile)
	if tips["enabled"] and tips["percentages"]:
		base = inv.net_total if tips["on"] == "Subtotal" else inv.grand_total
		t.rule().line(_("Suggested gratuity"), bold=True, align="center")
		for p in tips["percentages"]:
			tip = flt(base * p / 100, 2)
			t.cols(f"{p:g}%  {_('tip')} {_money(tip, inv.currency)}", f"{_('total')} {_money(flt(inv.grand_total) + tip, inv.currency)}")
	t.feed().line(_("Thank you!"), align="center")
	return t


def receipt_ticket(inv, width, drawer=False):
	t = Ticket(width)
	if drawer:
		t.drawer()
	order_name = frappe.db.get_value("Ren Order", {"link_invoice": inv.name}, "name")
	order = frappe.get_doc("Ren Order", order_name) if order_name else None
	_header(t, inv.company, order=order, inv=inv)
	_items(t, inv, inv.currency)
	t.rule()
	for p in inv.payments or []:
		if flt(p.amount):
			t.cols(p.mode_of_payment, _money(p.amount, inv.currency))
	if flt(inv.get("change_amount")):
		t.cols(_("Change"), _money(inv.change_amount, inv.currency), bold=True)
	t.feed().line(_("Thank you!"), align="center")
	return t


def _receipt_printer(pos_profile, required=True):
	name = frappe.get_cached_value("POS Profile", pos_profile, "ren_receipt_printer")
	if not name and required:
		frappe.throw(_("Set a Receipt Printer in POS Profile {0} (Restaurant tab)").format(pos_profile),
		             title=_("No printer"))
	return name


@frappe.whitelist()
def print_bill(order_name):
	order = get_order(order_name, "read")
	from renpos.api.invoicing import billing_profile_for
	printer = _receipt_printer(billing_profile_for(order))
	_p, width = _printer(printer)
	return queue_job(printer, "Bill", bill_ticket(order, width), "Ren Order", order.name)


@frappe.whitelist()
def print_receipt(invoice_doctype, invoice):
	require_restaurant_user()
	if invoice_doctype not in ("POS Invoice", "Sales Invoice"):
		raise frappe.PermissionError
	inv = frappe.get_doc(invoice_doctype, invoice)
	inv.check_permission("read")
	printer = _receipt_printer(inv.pos_profile)
	_p, width = _printer(printer)
	return queue_job(printer, "Receipt", receipt_ticket(inv, width), invoice_doctype, inv.name)


def after_payment(inv):
	"""Called by process_payment: receipt and/or cash drawer as configured."""
	profile = frappe.get_cached_doc("POS Profile", inv.pos_profile)
	printer = profile.get("ren_receipt_printer")
	if not printer:
		return None
	cash_modes = {m for m in (p.mode_of_payment for p in inv.payments or [])
	              if frappe.get_cached_value("Mode of Payment", m, "type") == "Cash"}
	drawer = cint(profile.get("ren_open_drawer_on_cash")) and any(
		flt(p.amount) for p in inv.payments or [] if p.mode_of_payment in cash_modes)
	_p, width = _printer(printer)
	if cint(profile.get("ren_print_receipt_on_payment")):
		return queue_job(printer, "Receipt", receipt_ticket(inv, width, drawer=drawer), inv.doctype, inv.name)
	if drawer:
		return queue_job(printer, "Drawer", Ticket(width).drawer(), inv.doctype, inv.name)
	return None


@frappe.whitelist()
def open_drawer(pos_profile, approval=None):
	"""No sale: open the drawer (role "open the cash drawer", or a manager PIN). Always audited."""
	require_restaurant_user()
	from renpos.api.guards import check_billing_profile
	check_billing_profile(pos_profile)
	from renpos.api.invoicing import can_take_payments
	from renpos.api import access
	if not can_take_payments():
		raise frappe.PermissionError(_("Only cashiers can open the cash drawer"))
	approver = access.require("open_drawer", pos_profile, approval=approval)
	access.audit("open_drawer", approved_by=approver, pos_profile=pos_profile)
	printer = _receipt_printer(pos_profile)
	_p, width = _printer(printer)
	return queue_job(printer, "Drawer", Ticket(width).drawer(), "POS Profile", pos_profile)

