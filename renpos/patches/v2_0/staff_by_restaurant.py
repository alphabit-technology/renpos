"""
Staff access moves from the POS Profile to the restaurant (2026-10): one Ren
Staff per person and restaurant with their role and access. The POS Profile
stays for charging (its "Applicable for Users" are the cashiers).

  - every person listed in a POS Profile of a restaurant becomes its staff;
    their Ren Staff Access records there are merged: the role of the default
    profile (else the first one set), every floor / room / table / station
  - the person's chosen profile ("Work at") becomes the chosen restaurant
  - orders get their restaurant; restaurants their POS Profile for orders
  - Ren Staff Access, its POS Profile button and client script go away
"""

import frappe
from frappe.utils import cint


def execute():
	frappe.reload_doc("ren_pos", "doctype", "ren_staff")
	frappe.reload_doc("ren_pos", "doctype", "ren_order")
	frappe.reload_doc("ren_pos", "doctype", "ren_restaurant")

	has_old = frappe.db.table_exists("Ren Staff Access")
	rows = frappe.db.sql("""
		SELECT pu.name AS pu, pu.user, pu.`default` AS is_default, p.ren_restaurant AS restaurant, p.name AS profile
		FROM `tabPOS Profile User` pu JOIN `tabPOS Profile` p ON p.name = pu.parent
		WHERE pu.parenttype = 'POS Profile' AND IFNULL(p.ren_restaurant, '') != '' AND IFNULL(pu.user, '') != ''
		ORDER BY pu.`default` DESC, p.creation ASC""", as_dict=True)

	merged = {}
	for r in rows:
		key = (r.user, r.restaurant)
		m = merged.setdefault(key, {"role": None, "default": 0, "grants": []})
		m["default"] = m["default"] or cint(r.is_default)
		if has_old:
			old = frappe.db.get_value("Ren Staff Access", {"pos_profile_user": r.pu}, ["name", "restaurant_role"],
			                          as_dict=True)
			if old:
				m["role"] = m["role"] or old.restaurant_role
				for g in frappe.db.sql("""SELECT object_type, object_name FROM `tabRen Access Grant`
						WHERE parenttype = 'Ren Staff Access' AND parent = %s ORDER BY idx""", old.name, as_dict=True):
					if (g.object_type, g.object_name) not in m["grants"] and g.object_type and g.object_name:
						m["grants"].append((g.object_type, g.object_name))

	from renpos.ren_pos.doctype.ren_staff.ren_staff import restaurant_of
	for (user, restaurant), m in merged.items():
		if frappe.db.exists("Ren Staff", {"user": user, "restaurant": restaurant}):
			continue
		if not frappe.db.exists("User", user) or not frappe.db.exists("Ren Restaurant", restaurant):
			continue
		doc = frappe.new_doc("Ren Staff")
		doc.update({"user": user, "restaurant": restaurant, "restaurant_role": m["role"],
		            "is_default": m["default"], "enabled": 1})
		for object_type, object_name in m["grants"]:
			# grants of another restaurant (a profile shared by mistake) don't move
			if frappe.db.exists(object_type, object_name) and restaurant_of(object_type, object_name) == restaurant:
				doc.append("restaurant_permissions", {"object_type": object_type, "object_name": object_name})
		doc.flags.ignore_permissions = True
		doc.insert()

	# one default restaurant per person
	for user in {u for u, _r in merged}:
		defaults = frappe.get_all("Ren Staff", filters={"user": user, "is_default": 1}, pluck="name",
		                          order_by="creation asc")
		for extra in defaults[1:]:
			frappe.db.set_value("Ren Staff", extra, "is_default", 0, update_modified=False)

	# "Work at" chose a profile; now it chooses a restaurant
	for d in frappe.db.sql("""SELECT parent, defvalue FROM `tabDefaultValue` WHERE defkey = 'rm_pos_profile'""",
	                       as_dict=True):
		restaurant = frappe.db.get_value("POS Profile", d.defvalue, "ren_restaurant")
		if restaurant:
			frappe.defaults.set_user_default("ren_current_restaurant", restaurant, d.parent)
	frappe.db.delete("DefaultValue", {"defkey": "rm_pos_profile"})

	# orders know their restaurant (their table's)
	frappe.db.sql("""UPDATE `tabRen Order` o
		JOIN `tabRen Table` t ON t.name = o.`table` JOIN `tabRen Room` r ON r.name = t.room
		JOIN `tabRen Floor` f ON f.name = r.floor
		SET o.restaurant = f.restaurant WHERE IFNULL(o.restaurant, '') = ''""")
	frappe.db.sql("""UPDATE `tabRen Order` o JOIN `tabPOS Profile` p ON p.name = o.pos_profile
		SET o.restaurant = p.ren_restaurant WHERE IFNULL(o.restaurant, '') = ''""")

	# each restaurant's profile for orders: its first one
	for name in frappe.get_all("Ren Restaurant", filters={"pos_profile": ["is", "not set"]}, pluck="name"):
		first = frappe.get_all("POS Profile", filters={"ren_restaurant": name, "disabled": 0}, pluck="name",
		                       order_by="creation asc", limit=1)
		if first:
			frappe.db.set_value("Ren Restaurant", name, "pos_profile", first[0], update_modified=False)

	# the old pieces
	for cf in frappe.get_all("Custom Field", filters={"dt": "POS Profile User", "fieldname": "restaurant_permission"},
	                         pluck="name"):
		frappe.delete_doc("Custom Field", cf, force=True, ignore_permissions=True)
	for cs in frappe.get_all("Client Script", filters={"dt": "POS Profile"}, fields=["name", "script"]):
		if "Ren Staff Access" in (cs.script or "") or "restaurant_permission" in (cs.script or ""):
			frappe.delete_doc("Client Script", cs.name, force=True, ignore_permissions=True)
	if has_old:
		frappe.db.delete("Ren Access Grant", {"parenttype": "Ren Staff Access"})
		if frappe.db.exists("DocType", "Ren Staff Access"):
			frappe.delete_doc("DocType", "Ren Staff Access", force=True, ignore_permissions=True, ignore_on_trash=True)
		frappe.db.sql_ddl("DROP TABLE IF EXISTS `tabRen Staff Access`")

	# grants show the current names
	for g in frappe.db.sql("""SELECT name, object_type, object_name FROM `tabRen Access Grant`""", as_dict=True):
		if g.object_type and frappe.db.table_exists(g.object_type) and frappe.db.exists(g.object_type, g.object_name):
			frappe.db.set_value("Ren Access Grant", g.name, "description",
			                    frappe.db.get_value(g.object_type, g.object_name, "description") or g.object_name,
			                    update_modified=False)
