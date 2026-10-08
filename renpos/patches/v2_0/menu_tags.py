"""Menu Tags: default dietary & allergen tags; items marked Veg get "Vegetarian"."""

import frappe


def execute():
	frappe.reload_doc("ren_pos", "doctype", "ren_menu_tag")
	frappe.reload_doc("ren_pos", "doctype", "ren_item_menu_tag")
	from renpos.api.menus import install_default_tags
	install_default_tags()
	if not frappe.db.has_column("Item", "item_type") or not frappe.db.exists("Ren Menu Tag", "Vegetarian"):
		return
	for code in frappe.get_all("Item", filters={"item_type": "Veg"}, pluck="name"):
		if frappe.db.exists("Ren Item Menu Tag", {"parenttype": "Item", "parent": code, "tag": "Vegetarian"}):
			continue
		frappe.get_doc({"doctype": "Ren Item Menu Tag", "parenttype": "Item", "parentfield": "ren_tags", "parent": code,
		                "tag": "Vegetarian", "idx": 1}).db_insert()
