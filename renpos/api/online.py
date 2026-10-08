# -*- coding: utf-8 -*-
# renpos/api/online.py
#
# Guests order from their phones (the /order page):
#
#   Pickup      /order?r=<restaurant>   Ren Restaurant "Take pickup orders
#               online". The order lands on the restaurant's pickup table
#               (a counter) with the guest's name, phone and pickup time.
#               ASAP orders go to the kitchen at once; orders for later are
#               held and fired `pickup_prep_minutes` before (fire_due_pickups,
#               every few minutes).
#   Delivery    /order?r=<restaurant>&d=<ZIP code>   "Guests order delivery
#               online" (api/delivery.py): the ZIP code picks the branch
#               (delivery_check); the order lands on its delivery table with the
#               address, the zone's fee and the time promised. The zone's
#               minimum order applies. Orders for later are held like pickups.
#   At a table  /order?t=<table QR code>  "Guests order from their table".
#               Lines are added to the table's open order (or a new one);
#               they go to the kitchen at once, or wait as pending lines for
#               the server to review and send ("Send table orders straight
#               to the kitchen").
#
# Prices are always the server's (menu price, else the price list; the
# options priced as in the POS): the guest sends items, quantities, options
# and notes, never prices or discounts. Only items on the menu in force, not
# sold out. Payment: at pickup / with the server (Order Manager, as usual).
#
# The guest follows the order at /order?o=<token> (status()).
# Guests' orders are owned by "Guest", so every server sees and works them.

import json
import re

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import (add_to_date, cint, escape_html, flt, get_datetime, now_datetime,
                          strip_html)

from renpos.api import menus

MAX_LINES = 40
MAX_QTY = 50
SLOT_MINUTES = 15
SLOT_HOURS = 6


# ─────────────────────────────────────────────
# Where the guest orders
# ─────────────────────────────────────────────

def profile_of(restaurant):
	"""The POS Profile guests' orders are taken with (the restaurant's own, see guards.restaurant_profile)."""
	from renpos.api.guards import restaurant_profile
	profile = restaurant_profile(restaurant)
	if not profile:
		frappe.throw(_("Online ordering isn't available right now"))
	return profile


def _restaurant_of_table(table):
	room = frappe.db.get_value("Ren Table", table, "room")
	return menus.restaurant_of_room(room), room


def context(t=None, r=None, d=None):
	"""
	{mode: "table" | "pickup" | "delivery", restaurant, table, room, pos_profile}
	for a table QR code (t), a restaurant (r) or a delivery from it to a ZIP code
	(r + d); throws if that kind of ordering is off.
	"""
	unavailable = _("Online ordering isn't available right now")
	if d:
		from renpos.api.delivery import normalize_zip, quote_for
		zipcode = normalize_zip(d)
		rest = frappe.db.get_value("Ren Restaurant", r, ["active", "delivery", "delivery_online", "delivery_table"],
		                           as_dict=True) if r else None
		if not zipcode or not rest or not cint(rest.active) or not cint(rest.delivery) \
				or not cint(rest.delivery_online) or not rest.delivery_table:
			frappe.throw(unavailable)
		q = quote_for(r, zipcode)
		if not q["in_zone"]:
			frappe.throw(_("We don't deliver to {0} from here").format(zipcode))
		_restaurant, room = _restaurant_of_table(rest.delivery_table)
		return frappe._dict(mode="delivery", restaurant=r, table=rest.delivery_table, room=room,
		                    pos_profile=profile_of(r), zip=zipcode, quote=q)
	if t:
		table = frappe.db.get_value("Ren Table", {"ren_qr_token": str(t)[:40]}, "name") if t else None
		if not table:
			frappe.throw(_("This QR code isn't valid anymore. Please ask your server."))
		restaurant, room = _restaurant_of_table(table)
		rest = frappe.db.get_value("Ren Restaurant", restaurant, ["active", "table_ordering"], as_dict=True) \
			if restaurant else None
		if not rest or not cint(rest.active) or not cint(rest.table_ordering):
			frappe.throw(_("Ordering from the table isn't available here. Please ask your server."))
		return frappe._dict(mode="table", restaurant=restaurant, table=table, room=room,
		                    pos_profile=profile_of(restaurant))
	if not r or not frappe.db.exists("Ren Restaurant", r):
		frappe.throw(unavailable)
	rest = frappe.db.get_value("Ren Restaurant", r, ["active", "online_ordering", "pickup_table"], as_dict=True)
	if not cint(rest.active) or not cint(rest.online_ordering) or not rest.pickup_table:
		frappe.throw(unavailable)
	_restaurant, room = _restaurant_of_table(rest.pickup_table)
	return frappe._dict(mode="pickup", restaurant=r, table=rest.pickup_table, room=room,
	                    pos_profile=profile_of(r))


def delivers_online():
	"""Some branch takes delivery orders online (the /order page offers delivery)."""
	return bool(frappe.get_all("Ren Restaurant", filters={"active": 1, "delivery": 1, "delivery_online": 1,
	                                                       "delivery_table": ["is", "set"]}, limit=1))


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=60, seconds=60 * 10)
def delivery_check(zipcode):
	"""The branch that delivers to the ZIP code: {restaurant, restaurant_name, zone, fee, minimum, eta_minutes}."""
	from renpos.api.delivery import branches_for, normalize_zip
	zipcode = normalize_zip(zipcode)
	if not zipcode:
		frappe.throw(_("Enter your 5-digit ZIP code"))
	found = branches_for(zipcode, online=True)
	if not found:
		frappe.throw(_("Sorry, we don't deliver to {0} yet").format(zipcode))
	q = found[0]
	return {k: q[k] for k in ("restaurant", "restaurant_name", "zone", "fee", "minimum", "eta_minutes")} | {"zip": zipcode}


def online_restaurants():
	"""Restaurants taking pickup orders (the /order page lists them)."""
	return frappe.get_all("Ren Restaurant", filters={"active": 1, "online_ordering": 1, "pickup_table": ["is", "set"]},
	                      fields=["name", "restaurant_name"], order_by="restaurant_name asc")


# ─────────────────────────────────────────────
# Menu
# ─────────────────────────────────────────────

ITEM_FIELDS = ("item_code", "item_name", "item_group", "description", "image", "price_list_rate", "has_variants",
               "variants", "variant_of", "variant_label", "modifier_groups", "price_from_components")


def _catalog(ctx):
	"""Items the guest can order: on the menu in force, not sold out, at the menu's prices."""
	from renpos.api.modifiers import catalog_for_items, modes_for
	from renpos.api.pos import get_items_with_prices
	from renpos.api.guards import effective_price_list

	profile = frappe.get_cached_doc("POS Profile", ctx.pos_profile)
	price_list = effective_price_list(profile.name)
	menu = menus.resolve_menu(room=ctx.room, restaurant=ctx.restaurant)
	items = get_items_with_prices(profile)

	order = {}
	if menu:
		rows = frappe.get_all("Ren Menu Item", filters={"parent": menu["name"], "parenttype": "Ren Menu",
		                                                     "enabled": 1}, pluck="item", order_by="idx asc")
		order = {code: i for i, code in enumerate(rows)}
		items = [i for i in items if i["item_code"] in order or i.get("variant_of") in order]
		prices = menus.menu_prices(menu["name"], [i["item_code"] for i in items])
		for i in items:
			if i["item_code"] in prices:
				i["price_list_rate"] = i["rate"] = prices[i["item_code"]]

	sold_out = menus.sold_out_items(ctx.restaurant)
	items = [i for i in items if i["item_code"] not in sold_out and i.get("variant_of") not in sold_out]
	# a template whose sizes all went away
	codes = {i["item_code"] for i in items}
	for i in items:
		if i.get("variants"):
			i["variants"]["variants"] = [v for v in i["variants"]["variants"] if v["item_code"] in codes]
			prices = [flt(x["price_list_rate"]) for x in items if x.get("variant_of") == i["item_code"]]
			if prices:
				i["price_list_rate"] = min(prices)
	items = [i for i in items if not i.get("variants") or i["variants"]["variants"]]

	groups = catalog_for_items(items, price_list)
	tags = menus.item_tags([i["item_code"] for i in items])
	out = []
	for i in items:
		row = {k: i.get(k) for k in ITEM_FIELDS}
		row["description"] = strip_html(row.get("description") or "").strip()[:300]
		if row["description"] == (row["item_name"] or ""):
			row["description"] = ""
		row["tags"] = tags.get(i["item_code"], [])
		row["sort"] = order.get(i["item_code"], order.get(i.get("variant_of"), 10 ** 6))
		out.append(row)
	out.sort(key=lambda x: (x["sort"], x["item_name"] or ""))
	return {
		"items": out,
		"modifier_groups": groups,
		"modifier_modes": modes_for(ctx.restaurant),
		"menu": menu,
		"price_list": price_list,
	}


def pickup_slots(restaurant, now=None, prep=None):
	"""Pickup (or delivery) times offered: ASAP, then every 15 minutes for the next hours."""
	now = now or now_datetime()
	prep = prep or cint(frappe.db.get_value("Ren Restaurant", restaurant, "pickup_prep_minutes")) or 20
	first = add_to_date(now, minutes=prep)
	# round up to the next quarter hour
	extra = (SLOT_MINUTES - first.minute % SLOT_MINUTES) % SLOT_MINUTES
	t = add_to_date(first, minutes=extra).replace(second=0, microsecond=0)
	if t <= first:
		t = add_to_date(t, minutes=SLOT_MINUTES)
	slots = []
	end = add_to_date(now, hours=SLOT_HOURS)
	while t <= end:
		slots.append(t.strftime("%Y-%m-%d %H:%M:%S"))
		t = add_to_date(t, minutes=SLOT_MINUTES)
	return prep, slots


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=120, seconds=60 * 10)
def menu(t=None, r=None, d=None):
	"""What the ordering page needs: the restaurant, the menu and its options."""
	ctx = context(t, r, d)
	rest = frappe.db.get_value("Ren Restaurant", ctx.restaurant, ["restaurant_name", "logo", "online_note"],
	                           as_dict=True)
	profile = frappe.get_cached_doc("POS Profile", ctx.pos_profile)
	data = _catalog(ctx)
	groups_order = []
	for i in data["items"]:
		if i["item_group"] not in groups_order and not i.get("variant_of"):
			groups_order.append(i["item_group"])
	out = {
		"mode": ctx.mode,
		"restaurant": {"name": ctx.restaurant, "title": rest.restaurant_name or ctx.restaurant,
		               "logo": rest.logo, "note": rest.online_note or ""},
		"table": frappe.db.get_value("Ren Table", ctx.table, "description") if ctx.mode == "table" else None,
		"currency": profile.currency or frappe.get_cached_value("Company", profile.company, "default_currency"),
		"tax_inclusive": cint(profile.get("ren_tax_inclusive")),
		"item_groups": groups_order,
		**{k: data[k] for k in ("items", "modifier_groups", "modifier_modes")},
	}
	if ctx.mode == "pickup":
		out["prep_minutes"], out["slots"] = pickup_slots(ctx.restaurant)
	if ctx.mode == "delivery":
		q = ctx.quote
		out["delivery"] = {"zip": ctx.zip, "zone": q["zone"], "fee": q["fee"], "minimum": q["minimum"],
		                   "eta_minutes": q["eta_minutes"]}
		out["prep_minutes"], out["slots"] = pickup_slots(ctx.restaurant, prep=q["eta_minutes"] or 45)
	return out


# ─────────────────────────────────────────────
# Placing the order
# ─────────────────────────────────────────────

def _clean_lines(items):
	if isinstance(items, str):
		items = json.loads(items or "[]")
	if not isinstance(items, list) or not items:
		frappe.throw(_("Your order is empty"))
	if len(items) > MAX_LINES:
		frappe.throw(_("That's a big order! Please call us."))
	lines = []
	for it in items:
		if not isinstance(it, dict) or not it.get("item_code"):
			frappe.throw(_("Invalid item"))
		qty = cint(it.get("qty"))
		if qty < 1 or qty > MAX_QTY:
			frappe.throw(_("Invalid quantity"))
		mods = it.get("modifiers") or []
		if isinstance(mods, str):
			mods = json.loads(mods or "[]")
		# the guest picks options; everything about price comes from the server
		mods = [{k: m.get(k) for k in ("option", "parent", "qty", "mode") if m.get(k) is not None}
		        for m in mods if isinstance(m, dict) and m.get("option")]
		lines.append({
			"identifier": "g-" + frappe.generate_hash(length=10),
			"item_code": str(it["item_code"])[:140],
			"qty": qty,
			"price_list_rate": 0, "rate": 0, "discount_percentage": 0, "modifiers_amount": 0,
			"item_tax_rate": "{}",
			"modifiers": mods,
			"notes": escape_html(str(it.get("notes") or "").strip()[:140]),
		})
	return lines


def _open_order(table):
	"""The table's open order (the latest), if any."""
	rows = frappe.get_all("Ren Order", filters={"table": table, "status": ["not in", ["Invoiced", "Cancelled", "Closed"]],
	                                              "link_invoice": ["in", ["", None]]},
	                      pluck="name", order_by="creation desc", limit=1)
	return frappe.get_doc("Ren Order", rows[0]) if rows else None


def _currency(ctx):
	profile = frappe.get_cached_doc("POS Profile", ctx.pos_profile)
	return profile.currency or frappe.get_cached_value("Company", profile.company, "default_currency")


def _phone(value):
	return re.sub(r"[^\d+()\- ]", "", value or "")[:30]


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60 * 60)
def place(items, t=None, r=None, d=None, guest_name=None, phone=None, pickup_at=None, notes=None,
          address_line=None):
	"""
	Place a guest's order. Returns {token, order} (token: follow it at /order?o=<token>).
	Pickup: `pickup_at` is when to pick it up; delivery: when to deliver it.
	"""
	from renpos.api import order as O
	from renpos.api import delivery as D

	ctx = context(t, r, d)
	guest_name = escape_html((guest_name or "").strip()[:80])
	phone = _phone(phone)
	lines = _clean_lines(items)

	pickup = None
	deliver_by = None
	delivery = ctx.mode == "delivery"
	address_line = escape_html((address_line or "").strip()[:200])
	if delivery and not address_line:
		frappe.throw(_("Please enter the delivery address"))
	if ctx.mode in ("pickup", "delivery"):
		if not guest_name or len(re.sub(r"\D", "", phone)) < 7:
			frappe.throw(_("Please enter your name and a phone number"))
		eta = (ctx.quote["eta_minutes"] or 45) if delivery else None
		prep, slots = pickup_slots(ctx.restaurant, prep=eta)
		if pickup_at:
			pickup = get_datetime(pickup_at)
			earliest = add_to_date(now_datetime(), minutes=prep - 2)
			if pickup < earliest or pickup > add_to_date(now_datetime(), hours=SLOT_HOURS, minutes=SLOT_MINUTES):
				frappe.throw(_("Please pick another pickup time"))
		else:
			pickup = add_to_date(now_datetime(), minutes=prep)
		if delivery:
			# `pickup` is when it reaches the guest; the kitchen has it ready the delivery time before
			deliver_by = pickup
			kitchen = cint(frappe.db.get_value("Ren Restaurant", ctx.restaurant, "pickup_prep_minutes")) or 20
			pickup = add_to_date(deliver_by, minutes=-(eta - min(kitchen, eta)))

	frappe.flags.ren_order_api = True
	frappe.flags.ren_guest_order = True
	try:
		order = _open_order(ctx.table) if ctx.mode == "table" else None
		new = order is None
		if new:
			order = frappe.get_doc({
				"doctype": "Ren Order", "table": ctx.table, "pos_profile": ctx.pos_profile,
				"status": "Draft", "attending_status": "Pending",
				"ren_origin": "Table QR" if ctx.mode == "table" else "Online",
				"ren_guest_name": guest_name, "ren_guest_phone": phone, "ren_pickup_time": pickup,
				"ren_guest_token": frappe.generate_hash(length=24),
			})
			if ctx.mode == "pickup":
				order.notes = _("Pickup {0} · {1} {2}").format(
					frappe.utils.format_datetime(pickup, "h:mm a"), guest_name, phone)
			if delivery:
				D.apply(order, ctx.quote, ctx.zip, address_line, deliver_by=deliver_by)
			order.insert(ignore_permissions=True)
		elif not order.get("ren_guest_token"):
			order.ren_guest_token = frappe.generate_hash(length=24)
			order.ren_origin = order.ren_origin or "Table QR"
		if ctx.mode == "table" and guest_name and not order.ren_guest_name:
			order.ren_guest_name = guest_name
		if notes:
			extra = escape_html(str(notes).strip()[:300])
			order.notes = f"{order.notes}\n{extra}".strip() if order.get("notes") else extra

		menu = menus.resolve_menu(room=ctx.room, restaurant=ctx.restaurant)
		hold = ctx.mode in ("pickup", "delivery") and pickup > add_to_date(
			now_datetime(), minutes=(cint(frappe.db.get_value("Ren Restaurant", ctx.restaurant, "pickup_prep_minutes")) or 20) + 5)
		for line in lines:
			code = line["item_code"]
			template = frappe.db.get_value("Item", code, "variant_of")
			if menu and not menus.in_menu(menu["name"], code) and not (template and menus.in_menu(menu["name"], template)):
				frappe.throw(_("{0} isn't on the menu right now").format(frappe.bold(code)))
			v = O._validate_item_calculation(line, order)
			order.append("entry_items", {
				"identifier": line["identifier"],
				"item_code": v["item_code"], "item_name": v["item_name"], "qty": flt(v["qty"]),
				"rate": flt(v["rate"]), "price_list_rate": flt(v["price_list_rate"]),
				"discount_percentage": flt(v["discount_percentage"]), "amount": flt(v["amount"]),
				"tax_amount": flt(v.get("tax_amount", 0)), "item_tax_rate": v["item_tax_rate"],
				"notes": line["notes"],
				"modifiers": json.dumps(v["modifiers"]) if v["modifiers"] else None,
				"modifiers_amount": flt(v["modifiers_amount"]),
				"ren_parts": O._parts(v),
				"ren_hold": 1 if hold else 0,
				"status": "Pending",
			})
		O._aggregate_order(order)
		missing = D.below_minimum(order)
		if missing:
			frappe.throw(_("The minimum order for delivery is {0}: add {1} more").format(
				frappe.utils.fmt_money(order.ren_delivery_minimum, currency=_currency(ctx)),
				frappe.utils.fmt_money(missing, currency=_currency(ctx))))
		order.save(ignore_permissions=True)

		identifiers = {l["identifier"] for l in lines}
		to_kitchen = ctx.mode in ("pickup", "delivery") and not hold or ctx.mode == "table" and cint(
			frappe.db.get_value("Ren Restaurant", ctx.restaurant, "table_orders_to_kitchen"))
		if to_kitchen:
			O._send(order, 0, only=identifiers)
		else:
			O._publish_order_event(order.table, order.name, "Add" if new else "update",
			                       data={"order": O._order_dict(order)} if new else None)
	finally:
		frappe.flags.ren_guest_order = False

	frappe.publish_realtime("ren_guest_order", {
		"order": order.name, "table": order.table, "mode": ctx.mode, "restaurant": ctx.restaurant, "sent": bool(to_kitchen), "held": bool(hold),
		"guest": guest_name, "lines": len(lines),
		"table_name": frappe.db.get_value("Ren Table", order.table, "description") or order.table,
		"pickup_time": str(pickup or ""),
	}, room=O._ORDER_ROOM, after_commit=True)
	return {"token": order.ren_guest_token, **_status(order)}


# ─────────────────────────────────────────────
# Following the order
# ─────────────────────────────────────────────

def _line_state(row):
	from renpos.api.parts import waiting_statuses
	from renpos.api.statuses import is_editable
	if is_editable(row.status):
		return "scheduled" if cint(row.get("ren_hold")) else "received"
	if row.status in waiting_statuses():
		return "preparing"
	return "ready"


STEPS = ("received", "scheduled", "preparing", "ready", "done")


def _status(order):
	lines = [r for r in order.entry_items if flt(r.qty) > 0]
	states = [_line_state(r) for r in lines]
	if order.link_invoice or order.status in ("Invoiced", "Closed"):
		state = "done"
	elif not states:
		state = "received"
	else:
		state = min(states, key=STEPS.index)  # the order is as far as its least advanced line
	if cint(order.get("ren_delivery")) and state != "done":
		# dispatch (api/dispatch.py): the driver took it / it was delivered
		if order.get("ren_delivered_at"):
			state = "delivered"
		elif order.get("ren_dispatched_at"):
			state = "on_the_way"
	return {
		"order": order.name[-5:],
		"state": state,
		"mode": "delivery" if cint(order.get("ren_delivery")) else "pickup" if order.ren_origin == "Online" else "table",
		"deliver_by": str(order.get("ren_deliver_by") or ""),
		"driver": (order.get("ren_driver_name") or "").split(" ")[0],
		"address": order.get("ren_delivery_address") or "",
		"delivery_fee": flt(order.get("ren_delivery_fee")) if cint(order.get("ren_delivery")) else 0,
		"restaurant": frappe.db.get_value("Ren Restaurant", order.restaurant, "restaurant_name"),
		"table": frappe.db.get_value("Ren Table", order.table, "description") if order.ren_origin == "Table QR" else None,
		"guest_name": order.ren_guest_name,
		"pickup_time": str(order.ren_pickup_time or ""),
		"total": flt(order.amount) + (flt(order.get("ren_delivery_fee")) if cint(order.get("ren_delivery")) else 0),
		"tax": flt(order.tax),
		"lines": [{"item_name": r.item_name, "qty": flt(r.qty), "amount": flt(r.amount), "state": s,
		           "texts": _texts(r.modifiers)} for r, s in zip(lines, states)],
	}


def _texts(modifiers):
	from renpos.api.modifiers import texts
	try:
		return texts(modifiers)
	except Exception:
		return []


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=240, seconds=60 * 10)
def status(token):
	if not token or len(str(token)) < 20:
		frappe.throw(_("Order not found"))
	name = frappe.db.get_value("Ren Order", {"ren_guest_token": str(token)[:40]}, "name")
	if not name:
		frappe.throw(_("Order not found"))
	return _status(frappe.get_doc("Ren Order", name))


# ─────────────────────────────────────────────
# Scheduled pickups
# ─────────────────────────────────────────────

def fire_due_pickups():
	"""Send held pickup orders to the kitchen when their prep time starts (scheduler, every few minutes)."""
	from renpos.api import order as O
	rows = frappe.db.sql("""
		SELECT DISTINCT o.name, o.ren_pickup_time, o.restaurant FROM `tabRen Order` o
		JOIN `tabRen Order Item` i ON i.parent = o.name AND i.parenttype = 'Ren Order'
		WHERE o.ren_origin = 'Online' AND o.ren_pickup_time IS NOT NULL AND i.ren_hold = 1
		  AND IFNULL(o.link_invoice, '') = '' AND o.status NOT IN ('Invoiced', 'Cancelled', 'Closed')
	""", as_dict=True)
	now = now_datetime()
	for r in rows:
		prep = cint(frappe.db.get_value("Ren Restaurant", r.restaurant, "pickup_prep_minutes")) or 20
		if add_to_date(get_datetime(r.ren_pickup_time), minutes=-prep) > now:
			continue
		try:
			frappe.flags.ren_order_api = True
			O._send(frappe.get_doc("Ren Order", r.name), fire=1)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title="Restaurant: scheduled pickup not sent", reference_doctype="Ren Order",
			                 reference_name=r.name)


# ─────────────────────────────────────────────
# QR codes of the tables
# ─────────────────────────────────────────────

def ensure_token(table):
	token = frappe.db.get_value("Ren Table", table, "ren_qr_token")
	if not token:
		token = frappe.generate_hash(length=16)
		frappe.db.set_value("Ren Table", table, "ren_qr_token", token, update_modified=False)
	return token


def qr_svg(data, scale=4):
	import io
	import pyqrcode
	buf = io.BytesIO()
	pyqrcode.create(data, error="M").svg(buf, scale=scale, omithw=True, xmldecl=False, svgns=True)
	return buf.getvalue().decode()


def table_qr_codes(restaurant):
	"""[{table, description, room, url, svg}] for every table of the restaurant (managers)."""
	from renpos.api.guards import is_manager
	if not is_manager():
		raise frappe.PermissionError(_("Only a restaurant manager can print the tables' QR codes"))
	base = frappe.utils.get_url("/order")
	pickup = frappe.db.get_value("Ren Restaurant", restaurant, "pickup_table")
	out = []
	for t in frappe.db.sql("""
		SELECT t.name, t.description, r.description AS room FROM `tabRen Table` t
		JOIN `tabRen Room` r ON r.name = t.room JOIN `tabRen Floor` f ON f.name = r.floor
		WHERE f.restaurant = %s ORDER BY r.description, t.description, t.name""", restaurant, as_dict=True):
		if t.name == pickup:
			continue  # the counter where pickup orders land
		url = f"{base}?t={ensure_token(t.name)}"
		out.append({"table": t.name, "description": t.description or t.name, "room": t.room, "url": url,
		            "svg": qr_svg(url)})
	return out


@frappe.whitelist()
def new_table_code(table):
	"""A new QR code for a table (the printed one stops working)."""
	from renpos.api.guards import is_manager
	if not is_manager():
		raise frappe.PermissionError(_("Only a restaurant manager can do this"))
	frappe.db.set_value("Ren Table", table, "ren_qr_token", frappe.generate_hash(length=16))
	return frappe.db.get_value("Ren Table", table, "ren_qr_token")
