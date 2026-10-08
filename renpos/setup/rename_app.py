# -*- coding: utf-8 -*-
"""
Move a site from the old app (restaurant_management, module "Restaurant
Management") to Ren POS (renpos, module "Ren POS"). Run it once per site,
after installing renpos in the bench and before `bench migrate`:

    bench get-app renpos <repo>            # or: the folder in apps/
    # sites/apps.txt: replace restaurant_management with renpos
    bench --site <site> renpos-migrate-site
    bench --site <site> migrate

It only changes database rows with plain SQL (frappe's helpers would load
the hooks of the old app, whose code is gone). Safe to run twice.
"""

import frappe

OLD_APP, NEW_APP = "restaurant_management", "renpos"
OLD_MODULE, NEW_MODULE = "Restaurant Management", "Ren POS"


def _tables():
	return {r[0] for r in frappe.db.sql("SHOW TABLES")}


def _link_fields(options):
	"""(doctype, fieldname) of every Link to `options`, standard and custom."""
	rows = frappe.db.sql("""SELECT parent, fieldname FROM `tabDocField`
		WHERE fieldtype = 'Link' AND options = %s""", options)
	rows += frappe.db.sql("""SELECT dt, fieldname FROM `tabCustom Field`
		WHERE fieldtype = 'Link' AND options = %s""", options)
	return {(dt, f) for dt, f in rows}


def _update(doctype, field, old, new, tables, prefix=False):
	table = f"tab{doctype}"
	if table not in tables:
		return 0
	if not frappe.db.sql(f"SHOW COLUMNS FROM `{table}` LIKE %s", field):
		return 0
	if prefix:
		frappe.db.sql(f"UPDATE `{table}` SET `{field}` = CONCAT(%s, SUBSTRING(`{field}`, %s)) WHERE `{field}` LIKE %s",
		              (new, len(old) + 1, old.replace("_", "\\_") + "%"))
	else:
		frappe.db.sql(f"UPDATE `{table}` SET `{field}` = %s WHERE `{field}` = %s", (new, old))
	return 1


def run():
	tables = _tables()
	log = []

	# 1. the installed app (the global list, the Installed Application rows and site_config)
	import json
	# plain SQL: frappe's helpers would load the hooks of the old, missing app
	for name, value in frappe.db.sql("""SELECT name, defvalue FROM `tabDefaultValue`
			WHERE parent IN ('__global', '__default') AND defkey = 'installed_apps'"""):
		apps = json.loads(value or "[]")
		if OLD_APP in apps:
			apps = [NEW_APP if a == OLD_APP else a for a in apps]
			frappe.db.sql("UPDATE `tabDefaultValue` SET defvalue = %s WHERE name = %s", (json.dumps(apps), name))
	frappe.db.sql("UPDATE `tabInstalled Application` SET app_name = %s WHERE app_name = %s", (NEW_APP, OLD_APP))
	conf_apps = frappe.local.conf.get("installed_apps")
	if conf_apps and OLD_APP in conf_apps:
		from frappe.installer import update_site_config
		update_site_config("installed_apps", [NEW_APP if a == OLD_APP else a for a in conf_apps])
	log.append("installed app")

	# 2. the module: its record and every Link to it (DocType, Report, Page, Workspace...)
	def module_exists(name):
		return frappe.db.sql("SELECT 1 FROM `tabModule Def` WHERE name = %s", name)

	if module_exists(OLD_MODULE):
		if module_exists(NEW_MODULE):
			frappe.db.sql("DELETE FROM `tabModule Def` WHERE name = %s", OLD_MODULE)
		else:
			frappe.db.sql("UPDATE `tabModule Def` SET name = %s, module_name = %s, app_name = %s WHERE name = %s",
			              (NEW_MODULE, NEW_MODULE, NEW_APP, OLD_MODULE))
	frappe.db.sql("UPDATE `tabModule Def` SET app_name = %s WHERE app_name = %s", (NEW_APP, OLD_APP))
	fields = _link_fields("Module Def")
	# some keep it as text (Workspace Sidebar.module)
	fields |= set(frappe.db.sql("SELECT parent, fieldname FROM `tabDocField` WHERE fieldname IN ('module', 'module_name')"))
	for dt, field in fields:
		_update(dt, field, OLD_MODULE, NEW_MODULE, tables)
	log.append("module")

	# 3. fields holding the app's name (Workspace Sidebar, Desktop Icon, Module Onboarding...)
	for dt, field in frappe.db.sql("""SELECT parent, fieldname FROM `tabDocField`
			WHERE fieldname IN ('app', 'app_name') AND fieldtype IN ('Data', 'Select', 'Autocomplete')"""):
		_update(dt, field, OLD_APP, NEW_APP, tables)
	log.append("app fields")

	# 4. dotted paths: patches already run, scheduled jobs, report / print format modules
	prefix = OLD_APP + "."
	_update("Patch Log", "patch", prefix, NEW_APP + ".", tables, prefix=True)
	for field in ("method", "name"):
		_update("Scheduled Job Type", field, prefix, NEW_APP + ".", tables, prefix=True)
	_update("Scheduled Job Log", "scheduled_job_type", prefix, NEW_APP + ".", tables, prefix=True)
	log.append("patches and jobs")

	frappe.db.commit()
	# the cached list of installed apps still names the old app
	try:
		frappe.cache.flushall()
	except Exception:
		pass
	print("Renamed to Ren POS:", ", ".join(log))
	print("Now run: bench --site", frappe.local.site, "migrate")
