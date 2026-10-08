# -*- coding: utf-8 -*-
# renpos/api/delivery.py
#
# Delivery orders, by phone (call center) or online.
#
#   Branches   every Ren Restaurant with "Take delivery orders" is a branch.
#              Its Delivery zones list the ZIP codes it covers (021* = every
#              ZIP code starting with 021) with a fee, a minimum order and a
#              delivery time.
#   Which one  the customer's ZIP code picks the branch (branches_for): the
#              zone that names the ZIP code exactly beats a prefix, then the
#              fastest, then the cheapest. A call center agent can choose
#              another branch (any branch that delivers; outside its zones
#              the fee is 0 and the agent decides).
#   The order  lands on the branch's delivery table with the address, the
#              zone, the fee and the time promised; it then works as any
#              order (kitchen, KDS, tickets). The fee is a charge on the
#              bill, booked to the branch's delivery fee account.
#
# Staff working several branches switch with api.restaurant.switch_restaurant.

import re

import frappe
from frappe import _

from renpos.api.guards import staff_restaurants
from frappe.utils import add_to_date, cint, escape_html, flt, now_datetime

ZIP_RE = re.compile(r"^\d{5}$")


# ─────────────────────────────────────────────
# ZIP codes and zones
# ─────────────────────────────────────────────

def normalize_zip(value):
	"""The 5-digit ZIP code in what was typed ("02128-1234" -> "02128"), else ""."""
	digits = re.sub(r"\D", "", str(value or ""))
	return digits[:5] if len(digits) >= 5 else ""


def zip_patterns(text):
	"""The ZIP codes / prefixes of a zone: "02128, 02129 021*" -> ["02128", "02129", "021*"]."""
	out = []
	for part in re.split(r"[\s,;]+", str(text or "")):
		part = part.strip()
		if not part:
			continue
		if part.endswith("*"):
			prefix = re.sub(r"\D", "", part[:-1])
			if prefix:
				out.append(prefix + "*")
		else:
			z = normalize_zip(part)
			if z:
				out.append(z)
	return out


def invalid_zip_patterns(text):
	return [p for p in re.split(r"[\s,;]+", str(text or "")) if p.strip() and not
	        (ZIP_RE.match(p.strip()) or re.match(r"^\d{1,4}\*$", p.strip()))]


def _match(zipcode, patterns):
	"""How well a ZIP code matches a zone: 100 exact, the prefix length for a prefix, 0 none."""
	best = 0
	for p in patterns:
		if p == zipcode:
			return 100
		if p.endswith("*") and zipcode.startswith(p[:-1]):
			best = max(best, len(p) - 1)
	return best


def _branches():
	return frappe.get_all("Ren Restaurant", filters={"active": 1, "delivery": 1, "delivery_table": ["is", "set"]},
	                      fields=["name", "restaurant_name", "delivery_table", "delivery_online"],
	                      order_by="restaurant_name asc")


def _zones(restaurant):
	return frappe.get_all("Ren Delivery Zone", filters={"parent": restaurant, "parenttype": "Ren Restaurant",
	                                                    "active": 1},
	                      fields=["zone_name", "zip_codes", "fee", "minimum_order", "eta_minutes"], order_by="idx asc")


def _quote(branch, zone, score):
	return {
		"restaurant": branch.name,
		"restaurant_name": branch.restaurant_name or branch.name,
		"zone": zone.zone_name if zone else "",
		"fee": flt(zone.fee) if zone else 0,
		"minimum": flt(zone.minimum_order) if zone else 0,
		"eta_minutes": cint(zone.eta_minutes) if zone else 0,
		"in_zone": bool(zone),
		"online": cint(branch.delivery_online),
		"score": score,
	}


def branches_for(zipcode, online=False):
	"""Branches that deliver to the ZIP code, the best first (see the top)."""
	zipcode = normalize_zip(zipcode)
	if not zipcode:
		return []
	found = []
	for b in _branches():
		if online and not cint(b.delivery_online):
			continue
		best = None
		for z in _zones(b.name):
			score = _match(zipcode, zip_patterns(z.zip_codes))
			if score and (best is None or (score, -cint(z.eta_minutes), -flt(z.fee)) >
			              (best[0], -cint(best[1].eta_minutes), -flt(best[1].fee))):
				best = (score, z)
		if best:
			found.append(_quote(b, best[1], best[0]))
	found.sort(key=lambda q: (-q["score"], q["eta_minutes"], q["fee"], q["restaurant_name"]))
	return found


def quote_for(restaurant, zipcode):
	"""What delivering to the ZIP code from that branch costs (outside its zones: no zone, no fee)."""
	b = next((x for x in _branches() if x.name == restaurant), None)
	if not b:
		frappe.throw(_("{0} doesn't take delivery orders").format(restaurant))
	q = next((x for x in branches_for(zipcode) if x["restaurant"] == restaurant), None)
	return q or _quote(b, None, 0)


# ─────────────────────────────────────────────
# Phone orders (staff)
# ─────────────────────────────────────────────

@frappe.whitelist()
def quote(zipcode):
	"""
	For the call center: the branches that deliver to the ZIP code (the
	recommended one first) and every other branch that delivers, to choose by hand.
	"""
	from renpos.api.guards import require_restaurant_user
	require_restaurant_user()
	zipcode = normalize_zip(zipcode)
	if not zipcode:
		frappe.throw(_("Enter a 5-digit ZIP code"))
	matches = branches_for(zipcode)
	inside = {q["restaurant"] for q in matches}
	others = [_quote(b, None, 0) for b in _branches() if b.name not in inside]
	return {"zip": zipcode, "branches": matches + others, "recommended": matches[0]["restaurant"] if matches else None,
	        "mine": {r: 1 for r in staff_restaurants()}}


def address_text(address):
	"""One line for the ticket: "12 Main St, Apt 3, Boston 02128"."""
	if not address:
		return ""
	a = frappe.db.get_value("Address", address, ["address_line1", "address_line2", "city", "pincode"], as_dict=True)
	if not a:
		return ""
	return ", ".join(x for x in (a.address_line1, a.address_line2, " ".join(y for y in (a.city, a.pincode) if y)) if x)


def _digits(value):
	return re.sub(r"\D", "", str(value or ""))


@frappe.whitelist()
def lookup(phone):
	"""
	For the call center: customers with that phone number (Customer mobile or
	their contacts), each with their addresses. Matches on the last 7+ digits.
	"""
	from renpos.api.guards import require_restaurant_user
	require_restaurant_user()
	digits = _digits(phone)
	if len(digits) < 7:
		return []
	tail = digits[-10:]
	like = "%" + "%".join(tail) + "%"  # tolerant of spaces, dashes and parentheses
	names = set(frappe.db.sql_list("SELECT name FROM `tabCustomer` WHERE disabled = 0 AND mobile_no LIKE %s LIMIT 20",
	                               like))
	names |= set(frappe.db.sql_list("""
		SELECT dl.link_name FROM `tabContact Phone` cp
		JOIN `tabDynamic Link` dl ON dl.parent = cp.parent AND dl.parenttype = 'Contact' AND dl.link_doctype = 'Customer'
		WHERE cp.phone LIKE %s LIMIT 20""", like))
	out = []
	for name in sorted(names)[:10]:
		c = frappe.db.get_value("Customer", name, ["name", "customer_name", "mobile_no", "disabled"], as_dict=True)
		if not c or c.disabled:
			continue
		out.append({"customer": c.name, "customer_name": c.customer_name, "phone": c.mobile_no or phone,
		            "addresses": addresses_of(c.name)})
	return out


def addresses_of(customer):
	rows = frappe.db.sql("""
		SELECT a.name, a.address_line1, a.address_line2, a.city, a.pincode FROM `tabAddress` a
		JOIN `tabDynamic Link` dl ON dl.parent = a.name AND dl.parenttype = 'Address'
		WHERE dl.link_doctype = 'Customer' AND dl.link_name = %s AND IFNULL(a.disabled, 0) = 0
		ORDER BY a.is_shipping_address DESC, a.modified DESC LIMIT 10""", customer, as_dict=True)
	return [{"address": r.name, "line": address_text(r.name), "zip": normalize_zip(r.pincode)} for r in rows]


def _new_customer(customer_name, phone, pos_profile):
	profile = frappe.get_cached_doc("POS Profile", pos_profile)
	doc = frappe.get_doc({
		"doctype": "Customer", "customer_name": customer_name, "customer_type": "Individual",
		"customer_group": profile.get("customer_group") or frappe.db.get_single_value("Selling Settings", "customer_group")
		or frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
		"territory": profile.get("territory") or frappe.db.get_single_value("Selling Settings", "territory")
		or frappe.db.get_value("Territory", {"is_group": 0}, "name"),
		"mobile_no": phone or None,
	})
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	return doc.name


def _new_address(customer, line1, city, zipcode, pos_profile):
	company = frappe.db.get_value("POS Profile", pos_profile, "company")
	doc = frappe.get_doc({
		"doctype": "Address", "address_title": frappe.db.get_value("Customer", customer, "customer_name") or customer,
		"address_type": "Shipping", "address_line1": line1, "city": city or "-", "pincode": zipcode,
		"country": frappe.get_cached_value("Company", company, "country") or frappe.db.get_default("country"),
		"is_shipping_address": 1,
		"links": [{"link_doctype": "Customer", "link_name": customer}],
	})
	doc.insert(ignore_permissions=True)
	return doc.name


@frappe.whitelist(methods=["POST"])
def new_order(zipcode, restaurant=None, customer=None, address=None, address_line=None, phone=None, notes=None,
              customer_name=None, city=None, save_address=0):
	"""
	A delivery order taken by phone. `restaurant`: the branch (default: the one
	the ZIP code picks). The person must work at that branch (Ren Staff).
	The customer: an existing one, or `customer_name` to create it; the address:
	an existing one (`address`) or typed (`address_line`, `city`; `save_address`
	keeps it on the customer). Returns where to open it:
	{order, table, room, floor, pos_profile, switch}.
	"""
	from renpos.api import order as O
	from renpos.api.guards import (require_restaurant_user, works_at, current_restaurant,
	                               current_pos_profile, restaurant_profile)
	from renpos.api.staff import require_clocked_in

	require_restaurant_user()
	from renpos.api.access import takes_orders
	if not takes_orders():
		raise frappe.PermissionError(_("Your role doesn't take orders"))
	require_clocked_in()
	zipcode = normalize_zip(zipcode)
	if not zipcode:
		frappe.throw(_("Enter a 5-digit ZIP code"))
	if not restaurant:
		matches = branches_for(zipcode)
		if not matches:
			frappe.throw(_("No branch delivers to {0}. Choose one by hand.").format(zipcode))
		restaurant = matches[0]["restaurant"]
	q = quote_for(restaurant, zipcode)
	if not works_at(restaurant):
		raise frappe.PermissionError(_("You don't work at {0}. A manager adds you in Ren Staff.")
		                             .format(q["restaurant_name"]))
	here = restaurant == current_restaurant()
	pos_profile = current_pos_profile() if here else restaurant_profile(restaurant)
	# working the branch is what counts: the delivery table is the branch's counter
	table = frappe.db.get_value("Ren Restaurant", restaurant, "delivery_table")

	if customer and not frappe.db.exists("Customer", customer):
		frappe.throw(_("Customer {0} not found").format(customer))
	if address and not frappe.db.exists("Address", address):
		frappe.throw(_("Address {0} not found").format(address))
	phone = re.sub(r"[^\d+()\- ]", "", phone or "")[:30]
	customer_name = (customer_name or "").strip()[:140]
	if not customer and customer_name:
		customer = _new_customer(customer_name, phone, pos_profile)
	typed = (address_line or "").strip()[:200]
	if typed and customer and cint(save_address):
		address = _new_address(customer, typed, (city or "").strip()[:80], zipcode, pos_profile)
		typed = ""
	if typed:
		line = escape_html(", ".join(x for x in (typed, (city or "").strip()[:80]) if x))
	else:
		line = address_text(address)
	if not line:
		frappe.throw(_("Enter the delivery address"))

	frappe.flags.ren_order_api = True
	order = frappe.get_doc({
		"doctype": "Ren Order", "table": table, "pos_profile": pos_profile,
		"status": "Draft", "attending_status": "Pending", "ren_origin": "Phone",
		"customer": customer or None, "address": address or None,
		"ren_guest_name": frappe.db.get_value("Customer", customer, "customer_name") if customer else "",
		"ren_guest_phone": phone,
	})
	apply(order, q, zipcode, line, notes)
	order.insert(ignore_permissions=True)
	O._publish_order_event(table, order.name, "Add", data={"order": O._order_dict(order)})

	room = frappe.db.get_value("Ren Table", table, "room")
	return {
		"order": order.name, "table": table, "room": room,
		"floor": frappe.db.get_value("Ren Room", room, "floor"),
		"pos_profile": pos_profile, "restaurant": restaurant,
		"switch": not here,
	}


def apply(order, q, zipcode, address_line, notes=None, deliver_by=None):
	"""Put the delivery on the order (address, zone, fee, minimum, time) and in its notes for the tickets."""
	order.ren_delivery = 1
	order.ren_delivery_address = address_line
	order.ren_delivery_zip = zipcode
	order.ren_delivery_zone = q["zone"] or _("Outside the zones")
	order.ren_delivery_fee = q["fee"]
	order.ren_delivery_minimum = q["minimum"]
	order.ren_deliver_by = deliver_by or add_to_date(now_datetime(), minutes=q["eta_minutes"] or 45)
	where = address_line if zipcode in address_line else f"{address_line} {zipcode}".strip()
	head = _("Delivery {0} · {1}").format(frappe.utils.format_datetime(order.ren_deliver_by, "h:mm a"), where)
	who = " ".join(x for x in (order.get("ren_guest_name"), order.get("ren_guest_phone")) if x)
	extra = escape_html(str(notes).strip()[:300]) if notes else ""
	order.notes = "\n".join(x for x in (head, who, extra) if x)


def takes_phone_orders():
	"""Some branch the person works delivers and they take orders (the POS shows the "Delivery" button)."""
	from renpos.api.access import takes_orders
	if not takes_orders():
		return False
	mine = set(staff_restaurants())
	return any(b.name in mine for b in _branches())


def below_minimum(order):
	"""The amount still missing to reach the zone's minimum order (0 when it's reached)."""
	if not cint(order.get("ren_delivery")):
		return 0
	return max(flt(order.get("ren_delivery_minimum")) - flt(order.amount), 0)


# ─────────────────────────────────────────────
# The fee on the bill
# ─────────────────────────────────────────────

def add_fee(inv, order, profile):
	"""The delivery fee as an Actual charge on the invoice (like the tip)."""
	fee = flt(order.get("ren_delivery_fee"))
	if not cint(order.get("ren_delivery")) or fee <= 0:
		return
	restaurant = profile.get("ren_restaurant")
	account = frappe.db.get_value("Ren Restaurant", restaurant, "delivery_fee_account") if restaurant else None
	if not account:
		frappe.throw(_("Set the Delivery fee account of {0} (Ren Restaurant > Delivery)").format(restaurant),
		             title=_("Delivery fee account missing"))
	inv.append("taxes", {
		"charge_type": "Actual",
		"account_head": account,
		"description": _("Delivery fee"),
		"tax_amount": fee,
		"cost_center": profile.cost_center or frappe.get_cached_value("Company", profile.company, "cost_center"),
	})
