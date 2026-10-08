# Online reservations page: /reserve (optionally /reserve?restaurant=<name>)

import frappe
from frappe import _

no_cache = 1


def get_context(context):
	from renpos.api.public_booking import online_restaurants

	restaurants = online_restaurants()
	wanted = frappe.form_dict.get("restaurant")
	if wanted:
		restaurants = [r for r in restaurants if r.restaurant == wanted] or restaurants
	context.restaurants = restaurants
	context.title = _("Book a Table")
	context.no_breadcrumbs = 1
	context.today = frappe.utils.today()
	return context
