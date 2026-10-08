import frappe


def execute():
    """
    An old version left a unique index on Ren Station.description: two
    floors couldn't both have a "Kitchen", and adding a center failed with
    "Description must be unique". The field isn't unique any more.
    """
    rows = frappe.db.sql("""SHOW INDEX FROM `tabRen Station` WHERE Column_name = 'description' AND Non_unique = 0""",
                         as_dict=True)
    for key in {r.Key_name for r in rows}:
        frappe.db.sql_ddl(f"ALTER TABLE `tabRen Station` DROP INDEX `{key}`")
