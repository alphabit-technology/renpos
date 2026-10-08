# Guests order from their phones: /order?r=<restaurant> (pickup), /order?r=<restaurant>&d=<ZIP>
# (delivery), /order?t=<table QR code>,
# /order?o=<token> (follow an order). The page is a small React app (frontend/src/guest,
# built to dist/js/guest.js); everything it needs comes from api/online.py.

import os

import frappe
from frappe import _

no_cache = 1


def _asset_version():
	path = frappe.get_app_path("renpos", "public", "dist", "js", "guest.js")
	try:
		return str(int(os.path.getmtime(path)))
	except OSError:
		return "0"


def get_context(context):
	from renpos.api.online import delivers_online, online_restaurants

	context.no_breadcrumbs = 1
	context.title = _("Order")
	context.boot = frappe.as_json({
		"restaurants": [{"name": r.name, "title": r.restaurant_name or r.name} for r in online_restaurants()],
		"delivery": delivers_online(),
		"csrf_token": frappe.sessions.get_csrf_token() if frappe.session.user != "Guest" else "",
		"lang": frappe.local.lang or "en",
	})
	context.asset_version = _asset_version()
	return context
