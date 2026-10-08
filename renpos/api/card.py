# renpos/api/card.py
#
# Card payments on Stripe Terminal readers (server-driven integration:
# BBPOS WisePOS E, Stripe Reader S700/S710). No SDK in the browser: the
# server creates the PaymentIntent, hands it to the reader and the payment
# screen polls the status.
#
#   Ren Settings (Card Payments tab)  secret key + readers
#   Ren Card Payment                 one row per PaymentIntent (audit)
#
# process_payment() only accepts a card row that references a Succeeded,
# unused Ren Card Payment for the same order and amount, so a card
# charge can't be invented by the client or used twice.

import frappe
import requests
from frappe import _
from frappe.utils import cint, flt

from renpos.api.guards import check_billing_profile, get_order, require_restaurant_user

STRIPE_API = "https://api.stripe.com/v1"
TIMEOUT = 20


# ─────────────────────────────────────────────
# Stripe HTTP
# ─────────────────────────────────────────────

def _secret_key():
	settings = frappe.get_cached_doc("Ren Settings")
	if not cint(settings.get("stripe_enabled")):
		frappe.throw(_("Stripe Terminal is not enabled (Ren Settings → Card Payments)"))
	key = settings.get_password("stripe_secret_key", raise_exception=False)
	if not key:
		frappe.throw(_("Set the Stripe Secret Key in Ren Settings → Card Payments"))
	return key


def stripe(method, path, data=None):
	"""Call the Stripe API; raises a readable error on failure. Patched in tests."""
	try:
		r = requests.request(method, f"{STRIPE_API}{path}", data=data, auth=(_secret_key(), ""), timeout=TIMEOUT)
	except requests.RequestException as e:
		frappe.throw(_("Could not reach Stripe: {0}").format(e), title=_("Card reader"))
	try:
		body = r.json() if r.content else {}
	except ValueError:
		body = {}
	if r.status_code >= 400:
		err = body.get("error") or {}
		frappe.throw(err.get("message") or _("Stripe error {0}").format(r.status_code), title=_("Card reader"))
	return body


def _minor_units(amount, currency):
	zero_decimal = {"jpy", "krw", "vnd", "clp", "pyg", "ugx", "xaf", "xof"}
	return int(round(flt(amount) * (1 if currency.lower() in zero_decimal else 100)))


# ─────────────────────────────────────────────
# Readers
# ─────────────────────────────────────────────

def readers_for(pos_profile):
	settings = frappe.get_cached_doc("Ren Settings")
	if not cint(settings.get("stripe_enabled")):
		return []
	return [
		{"reader": r.reader_id, "label": r.label, "mode_of_payment": r.mode_of_payment}
		for r in settings.get("stripe_readers") or []
		if not r.pos_profile or r.pos_profile == pos_profile
	]


@frappe.whitelist()
def get_readers(pos_profile):
	require_restaurant_user()
	check_billing_profile(pos_profile)
	return readers_for(pos_profile)


def _reader(pos_profile, reader_id):
	for r in readers_for(pos_profile):
		if r["reader"] == reader_id:
			return r
	frappe.throw(_("Card reader {0} is not configured for POS Profile {1}").format(reader_id, pos_profile))


def _require_cashier():
	from renpos.api.invoicing import can_take_payments
	if not can_take_payments():
		raise frappe.PermissionError(_("Only cashiers can charge cards"))


# ─────────────────────────────────────────────
# Payment flow
# ─────────────────────────────────────────────

@frappe.whitelist()
def start_card_payment(order_name, reader, amount):
	"""Create the PaymentIntent and show it on the reader. Returns the Card Payment row."""
	require_restaurant_user()
	_require_cashier()
	# one card flow at a time per order (two terminals can't both charge it)
	frappe.db.get_value("Ren Order", order_name, "name", for_update=True)
	order = get_order(order_name, "write")
	if order.status == "Invoiced" or order.link_invoice:
		frappe.throw(_("Order already invoiced"))
	from renpos.api.invoicing import billing_profile_for
	billing = billing_profile_for(order)
	r = _reader(billing, reader)
	amount = flt(amount, 2)
	if amount <= 0:
		frappe.throw(_("The card amount must be positive"))
	existing = order_card_payments(order.name)
	if any(p["status"] == "Pending" for p in existing):
		frappe.throw(_("A card payment for this order is already waiting on a reader"), title=_("Card reader"))
	# bill + a tip at most as large as the bill
	from renpos.api.invoicing import build_invoice_preview
	limit = flt(build_invoice_preview(order).grand_total) * 2
	if amount + sum(p["amount"] for p in existing) > limit + 0.005:
		frappe.throw(_("The card amount is larger than what is due"), title=_("Card reader"))

	currency = (frappe.get_cached_value("POS Profile", billing, "currency") or "USD").lower()
	pi = stripe("POST", "/payment_intents", {
		"amount": _minor_units(amount, currency),
		"currency": currency,
		"payment_method_types[]": "card_present",
		"capture_method": "automatic",
		"description": f"{order.name} · {order.table_description or order.table}",
		"metadata[order]": order.name,
		"metadata[site]": frappe.local.site,
	})
	doc = frappe.get_doc({
		"doctype": "Ren Card Payment",
		"status": "Pending",
		"amount": amount,
		"currency": currency.upper(),
		"mode_of_payment": r["mode_of_payment"],
		"order_name": order.name,
		"pos_profile": billing,
		"reader": reader,
		"payment_intent": pi["id"],
	}).insert(ignore_permissions=True)
	# commit before talking to the reader: the charge must never exist
	# only on Stripe's side
	if not frappe.flags.in_test:
		frappe.db.commit()

	try:
		stripe("POST", f"/terminal/readers/{reader}/process_payment_intent", {
			"payment_intent": pi["id"],
			"process_config[enable_customer_cancellation]": "true",
		})
	except frappe.ValidationError as e:
		_cancel_intent(pi["id"])
		doc.db_set({"status": "Failed", "failure_message": frappe.utils.strip_html(str(e)) or "reader error"})
		if not frappe.flags.in_test:
			frappe.db.commit()  # keep the failed row for the audit
		raise
	return _state(doc)


def _state(doc):
	return {"name": doc.name, "status": doc.status, "amount": flt(doc.amount), "card": doc.card,
	        "mode_of_payment": doc.mode_of_payment, "failure_message": doc.failure_message}


def _cancel_intent(pi):
	try:
		stripe("POST", f"/payment_intents/{pi}/cancel")
	except frappe.ValidationError:
		pass


def _card_label(pi):
	charge = (pi.get("latest_charge") if isinstance(pi.get("latest_charge"), dict) else None) or {}
	details = (charge.get("payment_method_details") or {}).get("card_present") or {}
	if details.get("last4"):
		return f"{(details.get('brand') or '').title()} ···· {details['last4']}".strip()
	return None


@frappe.whitelist()
def card_payment_status(name):
	"""Poll: Pending -> Succeeded | Failed | Canceled."""
	require_restaurant_user()
	doc = frappe.get_doc("Ren Card Payment", name)
	get_order(doc.order_name, "read")
	if doc.status != "Pending":
		return _state(doc)

	pi = stripe("GET", f"/payment_intents/{doc.payment_intent}?expand[]=latest_charge")
	if pi.get("status") == "succeeded":
		doc.db_set({"status": "Succeeded", "card": _card_label(pi)})
		return _state(doc)
	if pi.get("status") == "canceled":
		doc.db_set("status", "Canceled")
		return _state(doc)

	reader = stripe("GET", f"/terminal/readers/{doc.reader}")
	action = reader.get("action") or {}
	if action.get("status") == "failed" and \
			(action.get("process_payment_intent") or {}).get("payment_intent") == doc.payment_intent:
		# declined / canceled on the reader: this intent is done, a retry creates a new one
		_cancel_intent(doc.payment_intent)
		doc.db_set({"status": "Failed", "failure_message": action.get("failure_message") or action.get("failure_code")})
	return _state(doc)


@frappe.whitelist()
def cancel_card_payment(name):
	require_restaurant_user()
	doc = frappe.get_doc("Ren Card Payment", name)
	get_order(doc.order_name, "write")
	if doc.status != "Pending":
		return _state(doc)
	try:
		stripe("POST", f"/terminal/readers/{doc.reader}/cancel_action")
	except frappe.ValidationError:
		# the customer may already be paying: check before giving up
		return card_payment_status(name)
	_cancel_intent(doc.payment_intent)
	# the card may have been approved right before the cancel reached the reader
	pi = stripe("GET", f"/payment_intents/{doc.payment_intent}?expand[]=latest_charge")
	if pi.get("status") == "succeeded":
		doc.db_set({"status": "Succeeded", "card": _card_label(pi)})
	elif pi.get("status") == "canceled":
		doc.db_set("status", "Canceled")
	return _state(doc)


@frappe.whitelist()
def simulate_card(name, card="4242424242424242"):
	"""Test mode only: a simulated reader 'taps' a card."""
	require_restaurant_user()
	_require_cashier()
	if not _secret_key().startswith("sk_test_"):
		frappe.throw(_("Card simulation is only available with a Stripe test key"))
	doc = frappe.get_doc("Ren Card Payment", name)
	get_order(doc.order_name, "write")
	stripe("POST", f"/test_helpers/terminal/readers/{doc.reader}/present_payment_method",
	       {"card_present[number]": card, "type": "card_present"})
	return card_payment_status(name)


# ─────────────────────────────────────────────
# Used by process_payment
# ─────────────────────────────────────────────

def claim_card_payments(order, payments):
	"""
	Validate the card rows sent with process_payment. Returns the Card
	Payment names to link to the invoice once it is submitted.
	"""
	names = []
	from renpos.api.invoicing import billing_profile_for
	reader_modes = {r["mode_of_payment"] for r in readers_for(billing_profile_for(order))}
	for p in payments or []:
		name = p.get("card_payment")
		if not name:
			# a mode tied to a card reader is only paid through the reader
			if p.get("mode_of_payment") in reader_modes and flt(p.get("amount")):
				frappe.throw(_("{0} payments must be charged on the card reader").format(p.get("mode_of_payment")))
			continue
		if name in names:
			frappe.throw(_("Card payment {0} is listed twice").format(name))
		doc = frappe.db.get_value("Ren Card Payment", name,
		                          ["name", "status", "order_name", "amount", "mode_of_payment", "invoice"],
		                          as_dict=True, for_update=True)
		if not doc or doc.order_name != order.name:
			frappe.throw(_("Card payment {0} doesn't belong to this order").format(name))
		if doc.status != "Succeeded":
			frappe.throw(_("Card payment {0} was not approved").format(name))
		if doc.invoice:
			frappe.throw(_("Card payment {0} was already used").format(name))
		if abs(flt(doc.amount) - flt(p.get("amount"))) > 0.005 or doc.mode_of_payment != p.get("mode_of_payment"):
			frappe.throw(_("Card payment {0} doesn't match the amount charged on the card").format(name))
		names.append(name)
	return names


def order_card_payments(order_name):
	"""Approved-but-unused and in-progress card charges of an order."""
	return [
		{"name": r.name, "status": r.status, "amount": flt(r.amount), "mode_of_payment": r.mode_of_payment,
		 "card": r.card, "reader": r.reader}
		for r in frappe.get_all(
			"Ren Card Payment",
			filters={"order_name": order_name, "status": ["in", ["Pending", "Succeeded"]], "invoice": ["is", "not set"]},
			fields=["name", "status", "amount", "mode_of_payment", "card", "reader"],
			order_by="creation asc",
		)
	]


def link_card_payments(names, invoice):
	for name in names:
		frappe.db.set_value("Ren Card Payment", name,
		                    {"invoice_doctype": invoice.doctype, "invoice": invoice.name}, update_modified=False)
