# PIN login for registered restaurant terminals: /pos-login

import frappe

no_cache = 1


def get_context(context):
	context.no_header = 1
	context.no_breadcrumbs = 1
	context.title = frappe._("Staff Login")
	return context
