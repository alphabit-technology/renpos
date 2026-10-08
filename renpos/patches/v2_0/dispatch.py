"""
Dispatch (2026-10): statuses carry a meaning (Ready / Finished), "On the way"
asks for the driver, and a Driver role. Existing statuses keep what the
restaurant set; only empty meanings are filled.
"""

import frappe


def execute():
	for status, kind in (("Completed", "Ready"), ("Delivered", "Finished")):
		if frappe.db.exists("Ren Order Status", status) and not frappe.db.get_value("Ren Order Status", status, "kind"):
			frappe.db.set_value("Ren Order Status", status, "kind", kind, update_modified=False)
	if not frappe.db.exists("Ren Order Status", "On the way"):
		frappe.get_doc({"doctype": "Ren Order Status", "action": "On the way", "icon": "fa fa-truck",
		                "color": "#7c3aed", "message": "On the way", "action_message": "Dispatch",
		                "allows_to_edit_item": 0, "ask_driver": 1}).insert(ignore_permissions=True)
	if frappe.db.count("Ren Role") and not frappe.db.exists("Ren Role", "Driver"):
		from renpos.api.access import DEFAULT_ROLES, FLAGS
		flags = DEFAULT_ROLES["Driver"]
		doc = frappe.new_doc("Ren Role")
		doc.role_name = "Driver"
		for f in FLAGS + ["can_approve"]:
			doc.set(f, frappe.utils.cint(flags.get(f, 0)))
		doc.description = flags.get("description")
		doc.insert(ignore_permissions=True)
