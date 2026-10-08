# -*- coding: utf-8 -*-
from . import __version__ as app_version

app_name = "renpos"
app_title = "Ren POS"
app_publisher = "Quantum Bit Core"
app_description = "Restaurant point of sale for ERPNext"
app_icon = "octicon octicon-file-directory"
app_color = "grey"
app_email = "qubitcore.io@gmail.com"
app_license = "GPL-3.0"
source_link = "https://github.com/alphabit-technology/erpnext-restaurant"

after_migrate = "renpos.setup.install.after_install"
after_install = "renpos.setup.install.after_install"

# The React bundle (dist/js/restaurant.js + dist/css/index.css) is NOT
# included globally: the ren-pos page loads it on demand, so the
# rest of the Desk doesn't download it or get Tailwind's base styles.
# meta-form.js stays global: the POS edits rooms, tables and stations with MetaForm.
app_include_js = [
  "/assets/renpos/helper/js/meta-form.js",
]

# Staff only list/read orders and bookings of the restaurants they work at
permission_query_conditions = {
    "Ren Order": "renpos.api.access.table_order_query",
    "Ren Booking": "renpos.api.access.booking_query",
}

has_permission = {
    "Ren Order": "renpos.api.access.table_order_has_permission",
    "Ren Booking": "renpos.api.access.booking_has_permission",
}

SYNC = "renpos.api.sync.config_changed"

doc_events = {
    "Ren Booking": {
        "on_trash": "renpos.api.booking.on_booking_delete",
    },
    "Ren Order": {
        "on_update": "renpos.api.booking.on_table_order_update",
        "on_trash": "renpos.api.booking.on_table_order_trash",
    },
    # setup changes reload the open POS screens (api/sync.py); grants show
    # the current name of what they give (Ren Staff)
    **{dt: {"on_update": SYNC, "on_trash": SYNC} for dt in (
        "POS Profile", "Ren Restaurant", "Ren Settings", "Ren Role", "Ren Staff", "Ren Order Status")},
    **{dt: {"on_update": [SYNC, "renpos.api.staff.refresh_grant_labels"], "on_trash": SYNC} for dt in (
        "Ren Floor", "Ren Room", "Ren Table", "Ren Station")},
    "Item": {
        # options and sections (Restaurant tab); the recipe (BOM) belongs to the dish
        "validate": [
            "renpos.api.modifiers.validate_item",
            "renpos.api.recipes.item_validate",
        ],
        "on_update": "renpos.api.modifiers.publish_change",
    },
}

scheduler_events = {
    "cron": {
        "*/5 * * * *": [
            "renpos.api.booking.run_scheduled",
        ],
        # online pickup orders for later go to the kitchen when their prep time starts
        "*/2 * * * *": [
            "renpos.api.online.fire_due_pickups",
        ],
    },
    "daily": [
        # recipe ingredients of paid orders not taken out at a register close
        "renpos.api.recipes.post_pending_usage",
    ],
}
