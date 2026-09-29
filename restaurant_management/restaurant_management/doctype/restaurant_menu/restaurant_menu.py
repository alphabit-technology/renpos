"""
Restaurant Menu — Server-side logic.

- Auto-computes categories from item groups on validate
- Renders category summary HTML
- Validates no duplicate items
- Enforces single default menu per company
- Whitelisted methods for frontend (child table queries via frappe.db)
"""

import frappe
from restaurant_management.api.guards import require_restaurant_user
from frappe import _
from frappe.model.document import Document
from collections import Counter


class RestaurantMenu(Document):

    def validate(self):
        self._check_duplicates()
        self._compute_summary()

    def on_update(self):
        if self.is_default:
            self._clear_other_defaults()

    def _check_duplicates(self):
        """Prevent duplicate items in the same menu."""
        seen = set()
        for row in self.items:
            if row.item in seen:
                frappe.throw(
                    _("Item {0} is duplicated in row {1}").format(
                        frappe.bold(row.item_name or row.item), row.idx
                    ),
                    title=_("Duplicate Menu Item"),
                )
            seen.add(row.item)

    def _compute_summary(self):
        """Count total items and build category summary."""
        enabled_items = [r for r in self.items if r.enabled]
        self.total_items = len(enabled_items)

        group_counts = Counter(r.item_group for r in enabled_items if r.item_group)

        if group_counts:
            badges = []
            for group, count in sorted(group_counts.items()):
                badges.append(
                    f'<span class="badge" style="margin:2px;padding:4px 8px;">'
                    f'{group} ({count})</span>'
                )
            self.categories_html = "".join(badges)
        else:
            self.categories_html = '<p class="text-muted">No items added yet</p>'

    def _clear_other_defaults(self):
        """Ensure only one default menu per company."""
        frappe.db.sql(
            """
            UPDATE `tabRestaurant Menu`
            SET is_default = 0
            WHERE company = %s AND name != %s AND is_default = 1
            """,
            (self.company, self.name),
        )


# ─── Whitelisted Methods ─────────────────────────────────


@frappe.whitelist()
def get_menu_item_codes(menu_name):
    """
    Get list of item codes in a menu.
    Uses frappe.db.get_all to query child table directly.

    Returns: ["ITEM-001", "ITEM-002", ...]
    """
    require_restaurant_user()
    if not menu_name:
        return []

    rows = frappe.db.get_all(
        "Restaurant Menu Item",
        filters={"parent": menu_name, "parenttype": "Restaurant Menu", "enabled": 1},
        fields=["item"],
        order_by="idx asc",
    )
    return [r.item for r in rows]


@frappe.whitelist()
def get_items_for_tree(
    menu_name=None,
    item_groups=None,
    item_type=None,
    search=None,
    price_list=None,
    limit_start=0,
    limit_page_length=50,
):
    """
    Fetch items for ItemTree with server-side pagination and filtering.

    If menu_name is provided, only returns items that belong to that menu.
    Combines with item_group, item_type, and search filters.

    Args:
        menu_name: filter by Restaurant Menu (optional)
        item_groups: JSON list of item group names (optional)
        item_type: "Veg" or "Non-Veg" (optional)
        search: text search on item_name/item_code (optional)
        price_list: Price List name for pricing (optional)
        limit_start: pagination offset
        limit_page_length: page size

    Returns:
        list of item dicts with item_code, item_name, item_group,
        price_list_rate, image, item_type, is_available
    """
    require_restaurant_user()
    import json

    limit_start = int(limit_start)
    limit_page_length = int(limit_page_length)

    # ── Base filters ──
    filters = {"disabled": 0}

    # ── Menu filter (child table query) ──
    if menu_name:
        menu_item_codes = frappe.db.get_all(
            "Restaurant Menu Item",
            filters={
                "parent": menu_name,
                "parenttype": "Restaurant Menu",
                "enabled": 1,
            },
            fields=["item"],
            order_by="idx asc",
        )
        codes = [r.item for r in menu_item_codes]
        if not codes:
            return []
        filters["name"] = ["in", codes]

    # ── Item group filter ──
    if item_groups:
        if isinstance(item_groups, str):
            item_groups = json.loads(item_groups)
        if item_groups:
            filters["item_group"] = ["in", item_groups]

    # ── Item type filter ──
    if item_type == "Veg":
        filters["item_type"] = "Veg"
    elif item_type == "Non-Veg":
        filters["item_type"] = ["!=", "Veg"]

    # ── Search ──
    or_filters = None
    if search and search.strip():
        q = f"%{search.strip()}%"
        or_filters = [
            ["item_name", "like", q],
            ["item_code", "like", q],
        ]

    # ── Build fields list ──
    fields = [
        "name as item_code",
        "item_name",
        "item_group",
        "description",
        "image",
    ]

    meta = frappe.get_meta("Item")
    if meta.has_field("item_type"):
        fields.append("item_type")
    if meta.has_field("is_available"):
        fields.append("is_available")

    # ── Fetch items ──
    items = frappe.get_all(
        "Item",
        filters=filters,
        or_filters=or_filters,
        fields=fields,
        order_by="item_group asc, item_name asc",
        limit_start=limit_start,
        limit_page_length=limit_page_length,
    )

    if not items:
        return []

    # ── Fetch prices ──
    item_codes = [i["item_code"] for i in items]
    price_filters = {
        "item_code": ["in", item_codes],
        "selling": 1,
    }
    if price_list:
        price_filters["price_list"] = price_list

    prices = frappe.get_all(
        "Item Price",
        filters=price_filters,
        fields=["item_code", "price_list_rate"],
    )
    price_map = {p.item_code: p.price_list_rate for p in prices}

    for item in items:
        item["price_list_rate"] = price_map.get(item["item_code"], 0)

    return items