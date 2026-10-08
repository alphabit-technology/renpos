"""
Ren Menu Item.rate becomes an optional per-menu price. Older rows
copied the item's standard rate automatically and it was never used: clear
those so the price list keeps deciding.
"""

import frappe


def execute():
	frappe.db.sql("""
		UPDATE `tabRen Menu Item` mi JOIN `tabItem` i ON i.name = mi.item
		SET mi.rate = 0 WHERE IFNULL(mi.rate, 0) = IFNULL(i.standard_rate, 0)
	""")
