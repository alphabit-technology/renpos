# Printable QR codes of a restaurant's tables (managers): /table_qr?restaurant=<name>
# Each code opens /order?t=<the table's code>, where guests order from the table.

import frappe
from frappe import _

no_cache = 1


def get_context(context):
	from renpos.api.guards import is_manager
	from renpos.api.online import table_qr_codes

	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=" + frappe.utils.quote(frappe.request.full_path)
		raise frappe.Redirect
	if not is_manager():
		raise frappe.PermissionError(_("Only a restaurant manager can print the tables' QR codes"))
	restaurants = frappe.get_all("Ren Restaurant", filters={"active": 1}, fields=["name", "restaurant_name"],
	                             order_by="restaurant_name asc")
	wanted = frappe.form_dict.get("restaurant") or (restaurants[0].name if restaurants else None)
	context.restaurants = restaurants
	context.restaurant = wanted
	context.restaurant_title = frappe.db.get_value("Ren Restaurant", wanted, "restaurant_name") if wanted else ""
	context.enabled = bool(wanted and frappe.db.get_value("Ren Restaurant", wanted, "table_ordering"))
	context.codes = table_qr_codes(wanted) if wanted else []
	context.title = _("Table QR Codes")
	context.no_breadcrumbs = 1
	return context
