# -*- coding: utf-8 -*-
# renpos/api/variants.py
#
# Sizes (and any other attribute that makes a different product) are ERPNext
# Item Variants: a template ("Coke", Has Variants) and one real Item per
# value ("Coke-S", "Coke-L"), each with its own price, stock and recipe.
#
#   The POS shows the template once; the waiter picks the size and the order
#   line is the variant. The template is never sold (ERPNext doesn't allow it).
#   Options and sections are set on the template and every variant uses them,
#   unless a variant has its own.
#   Inside a combo, a component that is a template asks for its size; the
#   default size is included and bigger ones charge the difference.

import frappe
from frappe.utils import cint


def template_of(item_code):
    return frappe.get_cached_value("Item", item_code, "variant_of") if item_code else None


def variant_info(templates, only=None):
    """
    {template: {"attributes": ["Size", ...],
                "variants": [{"item_code", "values": {attribute: value}, "label": "Large"}]}}
    Enabled variants, in the order of the attribute's values. `only`: a set
    of item codes the variants must be in (e.g. what the POS can sell).
    """
    templates = [t for t in set(templates or []) if t]
    if not templates:
        return {}
    attrs = {}
    for r in frappe.get_all("Item Variant Attribute", filters={"parenttype": "Item", "parent": ["in", templates]},
                            fields=["parent", "attribute"], order_by="parent asc, idx asc"):
        attrs.setdefault(r.parent, []).append(r.attribute)
    variants = frappe.get_all("Item", filters={"variant_of": ["in", templates], "disabled": 0},
                              fields=["name", "variant_of"])
    if only is not None:
        variants = [v for v in variants if v.name in only]
    values = {}
    if variants:
        for r in frappe.get_all("Item Variant Attribute",
                                filters={"parenttype": "Item", "parent": ["in", [v.name for v in variants]]},
                                fields=["parent", "attribute", "attribute_value"]):
            values.setdefault(r.parent, {})[r.attribute] = r.attribute_value
    order = {}
    all_attrs = {a for lst in attrs.values() for a in lst}
    if all_attrs:
        for r in frappe.get_all("Item Attribute Value", filters={"parent": ["in", list(all_attrs)]},
                                fields=["parent", "attribute_value", "idx"]):
            order[(r.parent, r.attribute_value)] = cint(r.idx)

    out = {}
    for t in templates:
        names = attrs.get(t, [])
        rows = []
        for v in variants:
            if v.variant_of != t:
                continue
            vals = values.get(v.name, {})
            rows.append({"item_code": v.name, "values": vals,
                         "label": " ".join(str(vals[a]) for a in names if vals.get(a) not in (None, ""))
                                  or v.name})
        rows.sort(key=lambda r: tuple(order.get((a, r["values"].get(a)), 999) for a in names) + (r["item_code"],))
        if rows:
            out[t] = {"attributes": names, "variants": rows}
    return out


def label_of(item_code):
    """'Large' for a variant (its attribute values), '' otherwise."""
    template = template_of(item_code)
    if not template:
        return ""
    for v in variant_info([template]).get(template, {}).get("variants", []):
        if v["item_code"] == item_code:
            return v["label"]
    return ""


def display_name(item_code, item_name=None):
    """What waiters, tickets and screens show: 'Coke Large' for a variant, the item name otherwise."""
    template = template_of(item_code)
    if not template:
        return item_name or frappe.get_cached_value("Item", item_code, "item_name") or item_code
    label = label_of(item_code)
    base = frappe.get_cached_value("Item", template, "item_name") or template
    return f"{base} {label}".strip()
