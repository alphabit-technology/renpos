"""
Leftovers of the first version, removed from the code (cleanup, 2026-10):
the Restaurant Object / Desk Form system, unused DocTypes, the old desk
page record and dashboard chart, and the empty Customer client script.
"""

import frappe

DOCTYPES = ("Restaurant Object", "Desk Form Field", "Desk Form", "Restaurant Form", "Order Payment",
            "Item Customizable")


def execute():
	for doctype in DOCTYPES:
		if frappe.db.exists("DocType", doctype):
			frappe.delete_doc("DocType", doctype, force=True, ignore_permissions=True, ignore_on_trash=True)
		frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `tab{doctype}`")

	for doctype, name in (("Dashboard Chart", "Attending Orders"), ("Desk Page", "Restaurant Management")):
		if frappe.db.exists("DocType", doctype) and frappe.db.exists(doctype, name):
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)

	# the Customer client script had nothing left in it
	script = frappe.db.get_value("Client Script", "Customer-Form", "script") or ""
	if "crm_customer" in script:
		frappe.delete_doc("Client Script", "Customer-Form", force=True, ignore_permissions=True)
