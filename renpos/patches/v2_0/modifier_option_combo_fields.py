import frappe


def execute():
    """
    New Modifier Option fields (runs once, when they are added): every
    existing option is an Extra that changes the price and is chosen once
    at most, exactly how options worked before.
    """
    if not frappe.db.exists("DocType", "Modifier Option") or not frappe.db.has_column("Modifier Option", "option_type"):
        return
    frappe.db.sql("""UPDATE `tabModifier Option` SET option_type = 'Extra', affects_price = 1, max_qty = 1""")
