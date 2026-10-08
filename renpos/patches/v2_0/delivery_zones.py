"""
Delivery by zones (api/delivery.py) replaces the old delivery pieces: the
RM Delivery Charges / DC-POS Profile records, the branch restriction of the
stations (Production Center Branch) and the order's branch / delivery fields.
"""

from renpos.patches.v2_0.table_service import delete_doctypes, drop_columns

DOCTYPES = ("RM Delivery Charges", "DC-POS Profile", "Production Center Branch")

COLUMNS = {
	"Ren Order": ("delivery_charges", "delivery_date", "pick_time", "delivery_notes", "branch",
	                "customer_primary_address", "delivery_branch", "is_delivery", "charge_amount"),
	"Ren Order Item": ("branch",),
	"Ren Station": ("restricted_to_branches",),
}


def execute():
	delete_doctypes(DOCTYPES)
	drop_columns(COLUMNS)
