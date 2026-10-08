"""
Production centers are given one by one (a floor no longer gives its
stations): the roles that approve (Manager) get "Every production center",
a "Kitchen" role is added for cooks, and staff who only have stations and
no role get it.
"""

import frappe


def execute():
	frappe.db.sql("UPDATE `tabRen Role` SET all_stations = 1 WHERE can_approve = 1")
	if not frappe.db.exists("Ren Role", "Kitchen") and frappe.db.count("Ren Role"):
		from renpos.api.access import insert_default_role
		insert_default_role("Kitchen")
	for name in frappe.get_all("Ren Staff", filters={"restaurant_role": ["in", ["", None]]}, pluck="name"):
		types = set(frappe.get_all("Ren Access Grant", filters={"parenttype": "Ren Staff", "parent": name},
		                           pluck="object_type"))
		if types == {"Ren Station"}:
			frappe.db.set_value("Ren Staff", name, "restaurant_role", "Kitchen", update_modified=False)
