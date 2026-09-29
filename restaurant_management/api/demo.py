"""
Restaurant POS Demo Data Generator
===================================
Creates Item Groups (parent → child) and Items for a realistic restaurant demo.

Usage:
  - From browser console: frappe.call({ method: "erpnext_restaurant.api.demo.generate_demo_data" })
  - From bench console:   from erpnext_restaurant.api.demo import generate_demo_data; generate_demo_data()
  - To clean up:          frappe.call({ method: "erpnext_restaurant.api.demo.cleanup_demo_data" })

Adjust the file path in the decorator to match your app structure.
"""

import frappe
from frappe import _


# ─── Demo Data Definition ────────────────────────────────────────────

DEMO_PREFIX = "DEMO-"

ITEM_GROUPS = {
    "Food": [
        "Appetizers",
        "Main Course",
        "Sides",
        "Desserts",
    ],
    "Beverages": [
        "Soft Drinks",
        "Hot Drinks",
        "Beer",
        "Cocktails",
        "Wine",
    ],
}

ITEMS = {
    # ── Appetizers ────────────────────────────────
    "Appetizers": [
        {"code": "APP-001", "name": "Caesar Salad",          "rate": 8.50,  "item_type": "Veg"},
        {"code": "APP-002", "name": "Chicken Wings (8pc)",   "rate": 12.00, "item_type": "Non-Veg"},
        {"code": "APP-003", "name": "Mozzarella Sticks",     "rate": 7.50,  "item_type": "Veg"},
        {"code": "APP-004", "name": "Shrimp Cocktail",       "rate": 14.00, "item_type": "Non-Veg"},
        {"code": "APP-005", "name": "Tomato Soup",           "rate": 6.00,  "item_type": "Veg"},
        {"code": "APP-006", "name": "Garlic Bread",          "rate": 4.50,  "item_type": "Veg"},
        {"code": "APP-007", "name": "Nachos Supreme",        "rate": 10.00, "item_type": "Non-Veg"},
        {"code": "APP-008", "name": "Bruschetta",            "rate": 7.00,  "item_type": "Veg"},
    ],

    # ── Main Course ───────────────────────────────
    "Main Course": [
        {"code": "MNC-001", "name": "Grilled Ribeye Steak",       "rate": 28.00, "item_type": "Non-Veg"},
        {"code": "MNC-002", "name": "Chicken Alfredo Pasta",      "rate": 16.50, "item_type": "Non-Veg"},
        {"code": "MNC-003", "name": "Grilled Salmon Fillet",      "rate": 24.00, "item_type": "Non-Veg"},
        {"code": "MNC-004", "name": "Margherita Pizza",           "rate": 14.00, "item_type": "Veg"},
        {"code": "MNC-005", "name": "BBQ Bacon Cheeseburger",     "rate": 15.50, "item_type": "Non-Veg"},
        {"code": "MNC-006", "name": "Fish & Chips",               "rate": 13.00, "item_type": "Non-Veg"},
        {"code": "MNC-007", "name": "Mushroom Risotto",           "rate": 17.00, "item_type": "Veg"},
        {"code": "MNC-008", "name": "Chicken Parmesan",           "rate": 18.00, "item_type": "Non-Veg"},
        {"code": "MNC-009", "name": "Veggie Stir-Fry",            "rate": 13.50, "item_type": "Veg"},
        {"code": "MNC-010", "name": "Lamb Chops",                 "rate": 32.00, "item_type": "Non-Veg"},
        {"code": "MNC-011", "name": "Pepperoni Pizza",            "rate": 15.00, "item_type": "Non-Veg"},
        {"code": "MNC-012", "name": "Spaghetti Bolognese",        "rate": 14.50, "item_type": "Non-Veg"},
    ],

    # ── Sides ─────────────────────────────────────
    "Sides": [
        {"code": "SID-001", "name": "French Fries",          "rate": 4.50,  "item_type": "Veg"},
        {"code": "SID-002", "name": "Onion Rings",           "rate": 5.00,  "item_type": "Veg"},
        {"code": "SID-003", "name": "Steamed Rice",          "rate": 3.00,  "item_type": "Veg"},
        {"code": "SID-004", "name": "Coleslaw",              "rate": 3.50,  "item_type": "Veg"},
        {"code": "SID-005", "name": "Mashed Potatoes",       "rate": 4.00,  "item_type": "Veg"},
        {"code": "SID-006", "name": "Grilled Vegetables",    "rate": 5.50,  "item_type": "Veg"},
    ],

    # ── Desserts ──────────────────────────────────
    "Desserts": [
        {"code": "DST-001", "name": "Chocolate Brownie",     "rate": 7.00,  "item_type": "Veg"},
        {"code": "DST-002", "name": "Cheesecake Slice",      "rate": 8.50,  "item_type": "Veg"},
        {"code": "DST-003", "name": "Crème Brûlée",          "rate": 9.00,  "item_type": "Veg"},
        {"code": "DST-004", "name": "Tiramisu",              "rate": 8.00,  "item_type": "Veg"},
        {"code": "DST-005", "name": "Ice Cream (3 scoops)",  "rate": 6.00,  "item_type": "Veg"},
        {"code": "DST-006", "name": "Apple Pie à la Mode",   "rate": 7.50,  "item_type": "Veg"},
    ],

    # ── Soft Drinks ───────────────────────────────
    "Soft Drinks": [
        {"code": "SDK-001", "name": "Coca-Cola",             "rate": 2.50,  "item_type": "Veg"},
        {"code": "SDK-002", "name": "Sprite",                "rate": 2.50,  "item_type": "Veg"},
        {"code": "SDK-003", "name": "Orange Juice",          "rate": 3.50,  "item_type": "Veg"},
        {"code": "SDK-004", "name": "Lemonade",              "rate": 3.00,  "item_type": "Veg"},
        {"code": "SDK-005", "name": "Iced Tea",              "rate": 3.00,  "item_type": "Veg"},
        {"code": "SDK-006", "name": "Sparkling Water",       "rate": 2.00,  "item_type": "Veg"},
    ],

    # ── Hot Drinks ────────────────────────────────
    "Hot Drinks": [
        {"code": "HDK-001", "name": "Espresso",              "rate": 2.50,  "item_type": "Veg"},
        {"code": "HDK-002", "name": "Cappuccino",            "rate": 4.00,  "item_type": "Veg"},
        {"code": "HDK-003", "name": "Latte",                 "rate": 4.50,  "item_type": "Veg"},
        {"code": "HDK-004", "name": "Hot Chocolate",         "rate": 3.50,  "item_type": "Veg"},
        {"code": "HDK-005", "name": "Green Tea",             "rate": 3.00,  "item_type": "Veg"},
    ],

    # ── Beer ──────────────────────────────────────
    "Beer": [
        {"code": "BER-001", "name": "Corona Extra",          "rate": 5.00,  "item_type": "Veg"},
        {"code": "BER-002", "name": "Heineken",              "rate": 5.00,  "item_type": "Veg"},
        {"code": "BER-003", "name": "IPA Craft Beer",        "rate": 7.00,  "item_type": "Veg"},
        {"code": "BER-004", "name": "Guinness Stout",        "rate": 6.50,  "item_type": "Veg"},
        {"code": "BER-005", "name": "Modelo Especial",       "rate": 5.50,  "item_type": "Veg"},
    ],

    # ── Cocktails ─────────────────────────────────
    "Cocktails": [
        {"code": "CTL-001", "name": "Margarita",             "rate": 10.00, "item_type": "Veg"},
        {"code": "CTL-002", "name": "Mojito",                "rate": 11.00, "item_type": "Veg"},
        {"code": "CTL-003", "name": "Piña Colada",           "rate": 12.00, "item_type": "Veg"},
        {"code": "CTL-004", "name": "Old Fashioned",         "rate": 13.00, "item_type": "Veg"},
        {"code": "CTL-005", "name": "Cosmopolitan",          "rate": 11.50, "item_type": "Veg"},
        {"code": "CTL-006", "name": "Daiquiri",              "rate": 10.50, "item_type": "Veg"},
    ],

    # ── Wine ──────────────────────────────────────
    "Wine": [
        {"code": "WIN-001", "name": "House Red (Glass)",     "rate": 8.00,  "item_type": "Veg"},
        {"code": "WIN-002", "name": "House White (Glass)",   "rate": 8.00,  "item_type": "Veg"},
        {"code": "WIN-003", "name": "Cabernet Sauvignon",    "rate": 12.00, "item_type": "Veg"},
        {"code": "WIN-004", "name": "Chardonnay",            "rate": 11.00, "item_type": "Veg"},
        {"code": "WIN-005", "name": "Prosecco (Glass)",      "rate": 9.50,  "item_type": "Veg"},
    ],
}


# ─── Generator ────────────────────────────────────────────────────────

@frappe.whitelist()
def generate_demo_data():
    """Create all demo Item Groups and Items. Safe to run multiple times."""
    created = {"groups": [], "items": []}

    # 1. Ensure parent groups exist (Food, Beverages)
    for parent_group in ITEM_GROUPS:
        _ensure_item_group(parent_group, parent="All Item Groups")
        created["groups"].append(parent_group)

        # 2. Create child groups
        for child_group in ITEM_GROUPS[parent_group]:
            _ensure_item_group(child_group, parent=parent_group)
            created["groups"].append(f"  └─ {child_group}")

    # 3. Create items
    # Ensure default UOM exists
    _ensure_uom("Nos")

    for group_name, items in ITEMS.items():
        for item_def in items:
            item_code = f"{DEMO_PREFIX}{item_def['code']}"
            if not frappe.db.exists("Item", item_code):
                item = frappe.new_doc("Item")
                item.item_code = item_code
                item.item_name = item_def["name"]
                item.item_group = group_name
                item.stock_uom = "Nos"
                item.is_stock_item = 0
                item.include_item_in_manufacturing = 0
                item.standard_rate = item_def["rate"]

                # Custom fields for restaurant POS (if they exist)
                if hasattr(item, "item_type"):
                    item.item_type = item_def.get("item_type", "")

                item.flags.ignore_mandatory = True
                item.insert(ignore_permissions=True)
                created["items"].append(f"{item_code}: {item_def['name']}")

    # 4. Update price list
    _update_price_list(ITEMS)

    frappe.db.commit()

    summary = (
        f"Demo data created:\n"
        f"  • {len(created['groups'])} item groups\n"
        f"  • {len(created['items'])} items\n"
        f"  • Price list updated"
    )
    frappe.msgprint(_(summary), title=_("Demo Data Generated"), indicator="green")

    return created


@frappe.whitelist()
def cleanup_demo_data():
    """Remove all demo items (those with DEMO- prefix)."""
    deleted = 0

    items = frappe.get_all("Item", filters={"item_code": ["like", f"{DEMO_PREFIX}%"]}, pluck="name")
    for item_code in items:
        # Remove price list entries first
        frappe.db.delete("Item Price", {"item_code": item_code})
        frappe.delete_doc("Item", item_code, force=True, ignore_permissions=True)
        deleted += 1

    frappe.db.commit()
    frappe.msgprint(
        _(f"Cleaned up {deleted} demo items."),
        title=_("Demo Data Removed"),
        indicator="orange",
    )
    return {"deleted": deleted}


# ─── Helpers ──────────────────────────────────────────────────────────

def _ensure_item_group(name, parent="All Item Groups"):
    """Create an Item Group if it doesn't exist."""
    if not frappe.db.exists("Item Group", name):
        group = frappe.new_doc("Item Group")
        group.item_group_name = name
        group.parent_item_group = parent
        group.is_group = 1 if name in ITEM_GROUPS else 0
        group.flags.ignore_mandatory = True
        group.insert(ignore_permissions=True)


def _ensure_uom(uom_name):
    """Ensure a UOM exists."""
    if not frappe.db.exists("UOM", uom_name):
        uom = frappe.new_doc("UOM")
        uom.uom_name = uom_name
        uom.insert(ignore_permissions=True)


def _update_price_list(items_by_group):
    """Add/update Item Price entries in the default selling price list."""
    price_list = frappe.db.get_single_value("Selling Settings", "selling_price_list")
    if not price_list:
        price_list = "Standard Selling"
        if not frappe.db.exists("Price List", price_list):
            return  # No price list configured, skip

    for group_name, items in items_by_group.items():
        for item_def in items:
            item_code = f"{DEMO_PREFIX}{item_def['code']}"
            if not frappe.db.exists("Item", item_code):
                continue

            existing = frappe.db.exists("Item Price", {
                "item_code": item_code,
                "price_list": price_list,
            })

            if existing:
                frappe.db.set_value("Item Price", existing, "price_list_rate", item_def["rate"])
            else:
                ip = frappe.new_doc("Item Price")
                ip.item_code = item_code
                ip.price_list = price_list
                ip.price_list_rate = item_def["rate"]
                ip.flags.ignore_mandatory = True
                ip.insert(ignore_permissions=True)