"""
Ren Station "only these rooms / tables": the rows move from the old
Order Origin child table (which could only hold rooms and filtered on a
column that didn't exist) to Ren Station Room / Ren Station Table.
"""

import frappe


def execute():
	if frappe.db.table_exists("Order Origin"):
		rows = frappe.db.sql("""SELECT parent, origin, idx FROM `tabOrder Origin`
			WHERE parenttype = 'Ren Station' AND parentfield = 'restricted_rooms'""", as_dict=True)
		for r in rows:
			if not frappe.db.exists("Ren Room", r.origin):
				continue
			frappe.get_doc({"doctype": "Ren Station Room", "parenttype": "Ren Station", "parentfield": "restricted_rooms",
			                "parent": r.parent, "room": r.origin, "idx": r.idx}).db_insert()
	if frappe.db.exists("DocType", "Order Origin"):
		frappe.delete_doc("DocType", "Order Origin", force=True, ignore_permissions=True, ignore_on_trash=True)
	frappe.db.sql_ddl("DROP TABLE IF EXISTS `tabOrder Origin`")
