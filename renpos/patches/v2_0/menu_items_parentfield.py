import frappe


def execute():
    """
    Menu rows saved by the old floor-plan "add to menu" under the legacy
    `menu_items` field: the menu form and the Menu Manager use `items`, so
    those rows showed as "in the menu" but could never be removed. Move them
    to `items` (dropping any that are already there) and recount.
    """
    legacy = frappe.db.sql(
        """SELECT name, parent, item FROM `tabRen Menu Item`
        WHERE parenttype = 'Ren Menu' AND IFNULL(parentfield, '') != 'items'""",
        as_dict=True,
    )
    if not legacy:
        return
    for row in legacy:
        exists = frappe.db.exists("Ren Menu Item", {
            "parenttype": "Ren Menu", "parent": row.parent, "parentfield": "items", "item": row.item})
        if exists:
            frappe.db.delete("Ren Menu Item", {"name": row.name})
            continue
        idx = frappe.db.sql("""SELECT IFNULL(MAX(idx), 0) FROM `tabRen Menu Item`
            WHERE parenttype = 'Ren Menu' AND parent = %s AND parentfield = 'items'""", row.parent)[0][0]
        frappe.db.set_value("Ren Menu Item", row.name, {"parentfield": "items", "idx": idx + 1},
                            update_modified=False)
    for menu in {r.parent for r in legacy}:
        total = frappe.db.count("Ren Menu Item", {
            "parenttype": "Ren Menu", "parent": menu, "parentfield": "items", "enabled": 1})
        frappe.db.set_value("Ren Menu", menu, "total_items", total, update_modified=False)
