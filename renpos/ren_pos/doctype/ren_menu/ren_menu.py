"""
Ren Menu — Server-side logic.

- Auto-computes categories from item groups on validate
- Renders category summary HTML
- Validates no duplicate items
- Enforces single default menu per company
- Whitelisted methods for frontend (child table queries via frappe.db)
"""

import frappe
from renpos.api.guards import require_restaurant_user
from frappe import _
from frappe.model.document import Document
from collections import Counter


class RenMenu(Document):

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
            UPDATE `tabRen Menu`
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
        "Ren Menu Item",
        filters={"parent": menu_name, "parenttype": "Ren Menu", "enabled": 1},
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
    tag=None,
    price_list=None,
    limit_start=0,
    limit_page_length=50,
):
    """
    Fetch items for ItemTree with server-side pagination and filtering.

    If menu_name is provided, only returns items that belong to that menu.
    Combines with item_group, item_type, and search filters.

    Args:
        menu_name: filter by Ren Menu (optional)
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

    # ── Base filters ── (same rules the server applies when an item is ordered)
    # sizes are variants: the template is shown once, its variants are picked in the POS
    filters = {"disabled": 0, "is_sales_item": 1, "variant_of": ["is", "not set"]}

    # Prices must come from the POS price list the server validates against.
    if not price_list:
        from renpos.api.guards import current_pos_profile, effective_price_list
        profile = current_pos_profile()
        if profile:
            price_list = effective_price_list(profile)

    # ── Menu filter (child table query) ──
    menu_order = {}
    if menu_name:
        if not frappe.db.get_value("Ren Menu", menu_name, "enabled"):
            return []
        menu_item_codes = frappe.db.get_all(
            "Ren Menu Item",
            filters={
                "parent": menu_name,
                "parenttype": "Ren Menu",
                "enabled": 1,
            },
            fields=["item"],
            order_by="idx asc",
        )
        codes = [r.item for r in menu_item_codes]
        if not codes:
            return []
        filters["name"] = ["in", codes]
        menu_order = {c: i for i, c in enumerate(codes)}

    # ── Item group filter ──
    if item_groups:
        if isinstance(item_groups, str):
            item_groups = json.loads(item_groups)
        if item_groups:
            filters["item_group"] = ["in", item_groups]

    # ── Tag filter (Ren Menu Tag: Vegetarian, Gluten-free...) ──
    from renpos.api import menus
    if item_type and not tag and frappe.db.exists("Ren Menu Tag", item_type):
        tag, item_type = item_type, None
    if tag:
        tagged = menus.items_with_tag(tag)
        if "name" in filters:
            tagged = [c for c in tagged if c in set(filters["name"][1])]
        if not tagged:
            return []
        filters["name"] = ["in", tagged]

    # ── Item type filter (Veg / Non-Veg) ──
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
        "has_variants",
    ]

    meta = frappe.get_meta("Item")
    if meta.has_field("item_type"):
        fields.append("item_type")
    if meta.has_field("is_available"):
        fields.append("is_available")

    # ── Fetch items ── (a menu shows its items in the menu's own order)
    if menu_order:
        everything = frappe.get_all("Item", filters=filters, or_filters=or_filters, fields=fields)
        everything.sort(key=lambda i: menu_order.get(i["item_code"], 1e9))
        items = everything[limit_start:limit_start + limit_page_length]
    else:
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

    # ── Prices: the same rules the order uses (menu price, else price list) ──
    item_codes = [i["item_code"] for i in items]
    price_map = menus.list_prices(item_codes, price_list)
    price_map.update(menus.menu_prices(menu_name, item_codes))
    sold_out = menus.sold_out_items()
    tags = menus.item_tags(item_codes)

    # a template: "from" its cheapest variant
    templates = [i["item_code"] for i in items if i.get("has_variants")]
    if templates:
        variants = frappe.get_all("Item", filters={"variant_of": ["in", templates], "disabled": 0,
                                                  "is_sales_item": 1}, fields=["name", "variant_of"])
        vprices = menus.list_prices([v.name for v in variants], price_list)
        for v in variants:
            if v.name in vprices:
                cur = price_map.get(v.variant_of)
                price_map[v.variant_of] = vprices[v.name] if cur is None else min(cur, vprices[v.name])

    for item in items:
        item["price_list_rate"] = price_map.get(item["item_code"], 0)
        item["is_available"] = item["item_code"] not in sold_out and item.get("is_available", 1) not in (0, "0")
        item["tags"] = tags.get(item["item_code"], [])

    # items built from components: priced by their preselected options
    from renpos.api.modifiers import apply_component_prices
    apply_component_prices(items)

    return items

@frappe.whitelist()
def get_item_groups(menu_name=None):
    """
    Item Group tree for the POS catalog. Restaurant staff don't need
    read permission on Item Group (waiters usually don't have it).
    With a menu: only the groups (and their parents) that have items on it.
    """
    require_restaurant_user()
    groups = frappe.get_all(
        "Item Group",
        fields=["name", "parent_item_group", "is_group", "image", "lft", "rgt"],
        order_by="lft",
    )
    if not menu_name:
        return groups
    used = set(frappe.db.sql_list(
        """SELECT DISTINCT i.item_group FROM `tabRen Menu Item` mi JOIN `tabItem` i ON i.name = mi.item
        WHERE mi.parent = %s AND mi.parenttype = 'Ren Menu' AND mi.enabled = 1""", menu_name))
    spans = [(g.lft, g.rgt) for g in groups if g.name in used]
    return [g for g in groups if any(g.lft <= l and g.rgt >= r for l, r in spans)]
