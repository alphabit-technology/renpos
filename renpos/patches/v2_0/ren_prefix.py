# -*- coding: utf-8 -*-
"""
The app's own fields lose the old "rm_" (and "posa_") prefix for "ren_":

  - columns of Ren Order, Ren Order Item and Ren Table
  - custom fields added to ERPNext doctypes (Item, POS Profile, Customer,
    User, POS / Sales Invoice): the Custom Field record, its column, the
    child rows of its tables (parentfield), insert_after and Property Setters
  - the user default holding the restaurant someone works at
  - the "restaurant-manage" page, now "ren-pos"

Runs before the model sync, so the new definitions find their data in place.
Plain SQL only. Safe to run twice.
"""

import frappe

OWN_FIELDS = {
	"Ren Order": ["usage_entry", "origin", "guest_name", "guest_phone", "pickup_time", "guest_token", "delivery",
	              "delivery_address", "delivery_zip", "delivery_zone", "delivery_fee", "delivery_minimum",
	              "deliver_by", "driver", "driver_name", "dispatched_at", "delivered_at"],
	"Ren Order Item": ["parts", "part_status", "hold"],
	"Ren Table": ["qr_token"],
}

CHILD_TABLE_TYPES = ("Table", "Table MultiSelect")


def _columns(doctype):
	table = f"tab{doctype}"
	if not frappe.db.sql("SHOW TABLES LIKE %s", table):
		return set()
	return {r[0] for r in frappe.db.sql(f"SHOW COLUMNS FROM `{table}`")}


def _rename_column(doctype, old, new):
	cols = _columns(doctype)
	if old in cols and new not in cols:
		frappe.db.sql_ddl(f"ALTER TABLE `tab{doctype}` RENAME COLUMN `{old}` TO `{new}`")


def old_name(new):
	return "posa_tax_inclusive" if new == "ren_tax_inclusive" else "rm_" + new[len("ren_"):]


def execute():
	# 1. the app's own doctypes
	for doctype, names in OWN_FIELDS.items():
		for n in names:
			_rename_column(doctype, "rm_" + n, "ren_" + n)

	# 2. custom fields on ERPNext doctypes
	from renpos.setup.install import custom_fields
	for dt, fields in custom_fields.items():
		for new in fields:
			if not new.startswith("ren_"):
				continue
			old = old_name(new)
			row = frappe.db.sql("SELECT name, fieldtype, options FROM `tabCustom Field` WHERE dt = %s AND fieldname = %s",
			                    (dt, old), as_dict=True)
			if not row:
				continue
			row = row[0]
			if frappe.db.sql("SELECT 1 FROM `tabCustom Field` WHERE dt = %s AND fieldname = %s", (dt, new)):
				# already created under the new name (an earlier, partial run): drop the old record
				frappe.db.sql("DELETE FROM `tabCustom Field` WHERE name = %s", row.name)
			else:
				frappe.db.sql("UPDATE `tabCustom Field` SET name = %s, fieldname = %s WHERE name = %s",
				              (f"{dt}-{new}", new, row.name))
			_rename_column(dt, old, new)
			if row.fieldtype in CHILD_TABLE_TYPES and row.options:
				if "parentfield" in _columns(row.options):
					frappe.db.sql(f"UPDATE `tab{row.options}` SET parentfield = %s WHERE parentfield = %s AND parenttype = %s",
					              (new, old, dt))
			frappe.db.sql("UPDATE `tabCustom Field` SET insert_after = %s WHERE dt = %s AND insert_after = %s", (new, dt, old))
			for ps in frappe.db.sql("""SELECT name, property FROM `tabProperty Setter`
					WHERE doc_type = %s AND field_name = %s""", (dt, old), as_dict=True):
				frappe.db.sql("UPDATE `tabProperty Setter` SET field_name = %s, name = %s WHERE name = %s",
				              (new, f"{dt}-{new}-{ps.property}", ps.name))

	# 3. the restaurant each user works at
	frappe.db.sql("UPDATE `tabDefaultValue` SET defkey = 'ren_current_restaurant' WHERE defkey = 'rm_restaurant'")

	# 4. the page (the new one is synced from its files)
	frappe.db.sql("DELETE FROM `tabHas Role` WHERE parenttype = 'Page' AND parent = 'restaurant-manage'")
	frappe.db.sql("DELETE FROM `tabPage` WHERE name = 'restaurant-manage'")

	frappe.clear_cache()
