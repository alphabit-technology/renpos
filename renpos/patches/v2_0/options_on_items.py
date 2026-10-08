"""
Options move onto the Item (Restaurant tab: Sections + Options, shared
Option Lists). The old Modifier Groups are dropped, not converted (decided:
start clean); order lines keep the texts they were saved with.
"""

import frappe


def execute():
	for fieldname in ("Item-rm_modifier_groups", "Item Group-rm_modifier_groups"):
		if frappe.db.exists("Custom Field", fieldname):
			frappe.delete_doc("Custom Field", fieldname, force=True, ignore_permissions=True)
	if frappe.db.exists("Onboarding Step", "Add Modifiers"):
		frappe.db.set_value("Onboarding Step", "Add Modifiers", "reference_document", "Ren Option List")
	for doctype in ("Item Modifier Group", "Modifier Option", "Modifier Group"):
		if frappe.db.exists("DocType", doctype):
			frappe.delete_doc("DocType", doctype, force=True, ignore_permissions=True)
	frappe.clear_cache(doctype="Item")
