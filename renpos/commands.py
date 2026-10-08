# bench commands of Ren POS (bench loads <app>.commands for every app in apps.txt)

import click
from frappe.commands import get_site, pass_context


@click.command("renpos-migrate-site")
@pass_context
def renpos_migrate_site(context):
	"""Move a site from restaurant_management to renpos (run before `bench migrate`)."""
	import frappe
	from renpos.setup.rename_app import run

	site = get_site(context)
	frappe.init(site=site)
	frappe.connect()
	try:
		run()
	finally:
		frappe.destroy()


commands = [renpos_migrate_site]
