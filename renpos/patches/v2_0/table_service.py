"""
Table restrictions become one policy per restaurant (Ren Restaurant.table_service:
"Own tables" / "Team service"); the role's "work on other people's orders" is the
exception. The old restriction checks, exception lists and unused settings go.
"""

import frappe

DOCTYPES = ("Restaurant Exceptions", "Ren Access Grant Exception")

COLUMNS = {
	"Ren Restaurant": ("restrict_tables_by_owner", "restrict_orders_by_owner", "allow_multiple_pending_orders",
	                   "restriction_color", "shortcut_new_order", "shortcut_pay", "shortcut_transfer",
	                   "shortcut_change_status", "print_format", "kitchen_print_format", "enable_kds"),
}

SINGLE_FIELDS = {
	"Ren Settings": ("restricted_to_owner_table", "restricted_to_owner_order", "color",
	                        "multiple_pending_order"),
}


def drop_columns(columns):
	for doctype, fields in columns.items():
		existing = set(frappe.db.get_table_columns(doctype))
		for field in fields:
			if field in existing:
				frappe.db.sql_ddl(f"ALTER TABLE `tab{doctype}` DROP COLUMN `{field}`")


def drop_single_fields(fields_by_doctype):
	for doctype, fields in fields_by_doctype.items():
		frappe.db.delete("Singles", {"doctype": doctype, "field": ["in", fields]})


def delete_doctypes(doctypes):
	for doctype in doctypes:
		if frappe.db.exists("DocType", doctype):
			frappe.delete_doc("DocType", doctype, force=True, ignore_permissions=True, ignore_on_trash=True)
		frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `tab{doctype}`")


def execute():
	delete_doctypes(DOCTYPES)
	drop_columns(COLUMNS)
	drop_single_fields(SINGLE_FIELDS)
