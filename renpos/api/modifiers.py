# renpos/api/modifiers.py
#
# What can be chosen when an item is ordered, all set on the Item itself
# (Restaurant tab):
#
#   Options (Ren Item Option rows)   each one is
#       a component: another Item (an ingredient, a side, a drink, a whole
#                    dish inside a combo), Included (comes with the item and
#                    can be removed: "NO Tomato") or Optional (can be added:
#                    "Cheese x2", or chosen: "Salad"), or
#       an instruction: no component, just text for the kitchen ("Medium
#                    rare", "No salt").
#     price, changes_price, up to (max_qty), portion (qty), preselected,
#     default variant, unavailable (86).
#   Sections (Ren Item Option Section)  how the options are grouped and the rules
#     of each group: minimum / maximum choices, free choices, ingredient modes.
#     A section can pull a Ren Option List: options shared by many items
#     (Sauces, Cooking point...), offered next to the item's own.
#     "Price by size": its prices grow with the item's size, each size
#     (variant) multiplying them by its Option price factor (Large = 1.5).
#   ren_price_from_components     the price is the sum of what is chosen.
#
# Components are items, so they bring their own choices (one level): a
# burger inside a combo offers its own options under it ("Burger: NO
# Tomato"), and a component with variants asks for its size ("Coke: Large";
# the default size is included, bigger ones charge the difference).
# Sizes of the item itself are ERPNext variants (api/variants.py); a variant
# uses the template's options unless it has its own.
#
# Ren Modifier Mode (per restaurant): Light, Extra, On the side... offered on the
# options of sections with "Ingredient modes".
#
# At run time a section is a "group" {name, title, min_select, max_select,
# free_choices, use_modes, options} and an option is {id, label, price, item,
# ingredient_qty, included, is_default, affects_price, max_qty, nested:
# [group names it opens when chosen]}. The POS gets every group by name.
#
# Price of a line (per unit):
#   fixed price (default)   item price + the changes of options that change
#                           the price: optional ones add price x qty, an
#                           included one removed takes its price off, more
#                           units of an included one add the extra units.
#   price from components   the sum of the options chosen (price x qty).
# A mode adds price_factor x price per unit; a section's free choices take
# the cheapest optional units off. Never below 0.
#
# An order line stores the result in Ren Order Item.modifiers (JSON list,
# one entry per option chosen or included option removed) and the total of
# the changes in modifiers_amount, which is part of price_list_rate. Each
# entry carries `price` = its signed share of the unit price and `text` =
# what tickets and screens print ("NO Tomato", "Cheese x2", "Salad (instead
# of Fries)"; empty for included options left as they come). The client
# only sends option ids and quantities: labels, prices and rules always
# come from here.

import json

import frappe
from frappe import _
from frappe.utils import cint, flt

OPTIONS_FIELD = "ren_options"
SECTIONS_FIELD = "ren_option_sections"
DEFAULT_SECTION = ""


def _has(doctype, field):
	return frappe.get_meta(doctype).has_field(field)


def section_title(section):
	return section or _("Ingredients")


# ─────────────────────────────────────────────
# Loading
# ─────────────────────────────────────────────

class Catalog:
	"""
	Builds the groups of many items with a few queries. Prices of variant
	components come from `price_list`.
	"""

	def __init__(self, price_list=None):
		self.price_list = price_list
		self.groups = {}       # group name -> group
		self._built = {}       # config source item -> [its group names]
		self._meta = {}
		self._own = None
		self._lists = {}

	# items
	def meta(self, code):
		if code not in self._meta:
			fields = ["name", "item_name", "has_variants", "variant_of", "is_stock_item", "disabled"]
			if _has("Item", "ren_price_from_components"):
				fields.append("ren_price_from_components")
			self._meta[code] = frappe.db.get_value("Item", code, fields, as_dict=True) or frappe._dict(name=code)
		return self._meta[code]

	def prefetch(self, codes):
		codes = [c for c in set(codes) if c and c not in self._meta]
		if not codes:
			return
		fields = ["name", "item_name", "has_variants", "variant_of", "is_stock_item", "disabled"]
		if _has("Item", "ren_price_from_components"):
			fields.append("ren_price_from_components")
		for r in frappe.get_all("Item", filters={"name": ["in", codes]}, fields=fields):
			self._meta[r.name] = r

	def own(self):
		"""Items with options or sections of their own."""
		if self._own is None:
			self._own = set()
			if frappe.db.exists("DocType", "Ren Item Option"):
				for dt in ("Ren Item Option", "Ren Item Option Section"):
					self._own.update(frappe.get_all(dt, filters={"parenttype": "Item"}, pluck="parent", distinct=True))
		return self._own

	def source(self, code):
		"""The item whose options apply to `code`: itself, or its template."""
		if not code:
			return None
		if code in self.own():
			return code
		template = self.meta(code).get("variant_of")
		if template and template in self.own():
			return template
		return None

	def from_components(self, code):
		m = self.meta(code)
		if cint(m.get("ren_price_from_components")):
			return True
		template = m.get("variant_of")
		return bool(template and cint(self.meta(template).get("ren_price_from_components")))

	# groups
	def groups_for(self, item_code):
		src = self.source(item_code)
		if not src:
			return []
		self._build(src)
		names = list(self._built.get(src, []))
		factor = self.size_factor(item_code)
		if factor == 1:
			return names
		return [self._sized(n, item_code, factor) if self.groups[n].get("price_by_size") else n for n in names]

	def size_factor(self, item_code):
		"""A size (variant) multiplies the prices of "Price by size" sections by its Option price factor."""
		m = self.meta(item_code)
		if not m.get("variant_of"):
			return 1
		if "ren_option_factor" not in m:
			m["ren_option_factor"] = frappe.db.get_value("Item", item_code, "ren_option_factor") \
				if _has("Item", "ren_option_factor") else 1
		f = flt(m.get("ren_option_factor"))
		return f if f > 0 else 1

	def _sized(self, name, item_code, factor):
		"""
		The section priced for one size. Stored as "<group>@<size>" but it
		keeps the group's own name, so what was chosen survives a size change.
		"""
		key = f"{name}@{item_code}"
		if key not in self.groups:
			g = self.groups[name]
			self.groups[key] = {**g, "size_factor": factor,
			                    "options": [{**o, "price": flt(o["price"] * factor, 2)} for o in g["options"]]}
		return key

	def _list_rows(self, names):
		missing = [n for n in names if n not in self._lists]
		if missing:
			for n in missing:
				self._lists[n] = []
			for r in frappe.get_all("Ren Item Option", filters={"parenttype": "Ren Option List", "parent": ["in", missing],
			                                               "unavailable": 0},
			                        fields=["*"], order_by="parent asc, idx asc"):
				self._lists[r.parent].append(r)
		return {n: self._lists[n] for n in names}

	def _build(self, src):
		if src in self._built:
			return
		self._built[src] = []  # guards against loops (a component that contains its container)
		sfields = ["section", "option_list", "min_select", "max_select", "free_choices", "use_modes"]
		if _has("Ren Item Option Section", "price_by_size"):
			sfields.append("price_by_size")
		sections = frappe.get_all("Ren Item Option Section", filters={"parenttype": "Item", "parent": src},
		                          fields=sfields, order_by="idx asc")
		rows = frappe.get_all("Ren Item Option", filters={"parenttype": "Item", "parent": src, "unavailable": 0},
		                      fields=["*"], order_by="idx asc")
		lists = self._list_rows([s.option_list for s in sections if s.option_list])
		self.prefetch([r.item for r in rows] + [r.item for lst in lists.values() for r in lst])

		# shown in the Sections table's order; a section that isn't there goes
		# where its options are listed
		rules = {}
		for s in sections:
			rules.setdefault((s.section or "").strip(), s)
		table = list(rules)
		order = []

		def add(key):
			if key not in order:
				order.append(key)

		for key in [(r.section or "").strip() for r in rows]:
			if key in table:
				for k in table[:table.index(key) + 1]:
					add(k)
			else:
				add(key)
				rules[key] = frappe._dict(section=key)
		for k in table:
			add(k)

		names = []
		for key in order:
			rule = rules[key]
			opts = list(lists.get(rule.get("option_list"), [])) + [r for r in rows if (r.section or "").strip() == key]
			if not opts:
				continue
			name = f"{src}|{key}"
			group = {
				"name": name,
				"title": section_title(key),
				"min_select": cint(rule.get("min_select")),
				"max_select": cint(rule.get("max_select")),
				"free_choices": cint(rule.get("free_choices")),
				"use_modes": cint(rule.get("use_modes")),
				"price_by_size": cint(rule.get("price_by_size")),
				"options": [],
			}
			self.groups[name] = group
			group["options"] = [self._option(r, src) for r in opts]
			names.append(name)
		self._built[src] = names

	def _option(self, r, src):
		comp = r.item or None
		m = self.meta(comp) if comp else frappe._dict()
		included = 1 if r.role == "Included" else 0
		affects = 1 if r.changes_price is None or cint(r.changes_price) else 0
		opt = {
			"id": r.name,
			"label": r.label or m.get("item_name") or comp or "",
			"price": flt(r.price),
			"item": comp,
			"ingredient_qty": flt(r.qty) or 1,
			"included": included,
			"is_default": 1 if included else cint(r.preselected),
			"affects_price": affects,
			"max_qty": max(cint(r.max_qty), 1),
			"nested": [],
		}
		if comp:
			if cint(m.get("has_variants")):
				g = self._variant_group(comp, r.variant, affects)
				if g:
					opt["nested"].append(g)
			sub = self.source(comp)
			if sub and sub != src:
				self._build(sub)
				opt["nested"] += self._built.get(sub, [])
		return opt

	def _variant_group(self, template, default, affects):
		from renpos.api.menus import list_prices
		from renpos.api.variants import variant_info
		info = variant_info([template]).get(template)
		if not info:
			return None
		codes = [v["item_code"] for v in info["variants"]]
		prices = list_prices(codes, self.price_list) if self.price_list else {}
		if default not in codes:
			default = min(codes, key=lambda c: (flt(prices.get(c)), codes.index(c)))
		name = f"{template}|size|{default}|{affects}"
		if name in self.groups:
			return name
		base = flt(prices.get(default))
		self.groups[name] = {
			"name": name,
			"title": " / ".join(info["attributes"]) or _("Size"),
			"min_select": 1,
			"max_select": 1,
			"free_choices": 0,
			"use_modes": 0,
			"variants": 1,
			"options": [{
				"id": f"{template}::{v['item_code']}",
				"label": v["label"],
				"price": flt(flt(prices.get(v["item_code"])) - base, 2),
				"item": v["item_code"],
				"ingredient_qty": 1,
				"included": 0,
				"is_default": 1 if v["item_code"] == default else 0,
				"affects_price": affects,
				"max_qty": 1,
				"nested": [],
				"variant": 1,
			} for v in info["variants"]],
		}
		return name


def modes_for(restaurant=None):
	"""Modifier Modes offered in a restaurant (its own and the shared ones), in order."""
	if not frappe.db.exists("DocType", "Ren Modifier Mode"):
		return []
	rows = frappe.get_all("Ren Modifier Mode", filters={"enabled": 1},
	                      fields=["name", "mode_name", "restaurant", "kitchen_text", "price_factor", "qty_factor"],
	                      order_by="sort_order asc, creation asc")
	return [{"name": r.name, "label": r.mode_name, "kitchen_text": r.kitchen_text or "{0}",
	         "price_factor": flt(r.price_factor), "qty_factor": flt(r.qty_factor)}
	        for r in rows if not r.restaurant or r.restaurant == restaurant]


DEFAULT_MODES = [
	# label, kitchen text, price factor, portion factor
	("Light", "LIGHT {0}", 0, 0.5),
	("Extra", "EXTRA {0}", 1, 2),
	("On the side", "{0} ON THE SIDE", 0, 1),
]


def install_default_modes():
	"""Light, Extra and On the side for every restaurant (only when there are none)."""
	if not frappe.db.exists("DocType", "Ren Modifier Mode") or frappe.db.count("Ren Modifier Mode"):
		return
	for i, (label, text, price, portion) in enumerate(DEFAULT_MODES):
		frappe.get_doc({"doctype": "Ren Modifier Mode", "mode_name": label, "kitchen_text": text, "enabled": 1,
		                "price_factor": price, "qty_factor": portion, "sort_order": i}).insert(ignore_permissions=True)


def catalog_for_items(items, price_list=None):
	"""
	For get_pos_data: sets item["modifier_groups"] = [names] on each item
	dict (item_code) and returns every group used (nested ones included).
	"""
	cat = Catalog(price_list)
	cat.prefetch([i["item_code"] for i in items])
	for item in items:
		item["modifier_groups"] = cat.groups_for(item["item_code"])
	apply_component_prices(items, cat)
	return cat.groups


def _default_total(cat, names):
	"""Price of the options that come checked (and the defaults of what they open), priced from components."""
	total = 0
	for n in names:
		for o in cat.groups.get(n, {}).get("options", []):
			if o["is_default"]:
				total += option_share(o, 1, True)
				total += _default_total(cat, o["nested"]) if o["nested"] else 0
	return total


def apply_component_prices(items, cat=None):
	"""
	Items priced from components: price_from_components = 1 and, as their
	catalog price, the sum of what comes checked.
	"""
	if not items or not _has("Item", "ren_price_from_components"):
		return
	cat = cat or Catalog()
	cat.prefetch([i["item_code"] for i in items])
	for item in items:
		if not cat.from_components(item["item_code"]):
			continue
		price = flt(_default_total(cat, cat.groups_for(item["item_code"])), 2)
		item["price_from_components"] = 1
		item["price_list_rate"] = price
		if "rate" in item:
			item["rate"] = price


# ─────────────────────────────────────────────
# Validation (server is the source of truth)
# ─────────────────────────────────────────────

def _selected(selected):
	"""
	Client choice -> {(parent option or None, option id): {qty, mode}}: ids, or
	{option|id, qty, mode, parent} dicts. Repeated choices add up.
	"""
	if isinstance(selected, str):
		selected = json.loads(selected or "[]")
	out = {}
	for s in selected or []:
		if isinstance(s, dict):
			if s.get("removed"):
				continue  # removals are worked out here, not taken from the client
			oid = s.get("option") or s.get("id")
			qty = cint(s.get("qty")) if s.get("qty") not in (None, "") else 1
			mode = s.get("mode") or None
			parent = s.get("parent") or None
		else:
			oid, qty, mode, parent = s, 1, None, None
		if oid and qty > 0:
			key = (str(parent) if parent else None, str(oid))
			cur = out.setdefault(key, {"qty": 0, "mode": mode})
			cur["qty"] += qty
			cur["mode"] = mode or cur["mode"]
	return out


def price_from_components(item_code):
	return Catalog().from_components(item_code) if _has("Item", "ren_price_from_components") else False


def option_share(opt, qty, from_components, mode=None):
	"""Signed share of one option in the unit price (qty 0 = an included option removed)."""
	if not opt.get("affects_price", 1):
		return 0
	price = flt(opt["price"])
	extra = flt(mode["price_factor"]) * price * qty if mode and qty else 0
	if from_components:
		return price * qty + extra
	if opt.get("included"):
		return price * (qty - 1) + extra  # removed: -price; as it comes: 0; extra units: +price each
	return price * qty + extra


def entry_text(entry):
	if entry.get("removed"):
		return _("NO {0}").format(entry["label"])
	qty = cint(entry.get("qty")) or 1
	if entry.get("included") and qty == 1 and not entry.get("instead_of") and not entry.get("mode"):
		return ""  # as it comes: nothing to tell the kitchen
	text = entry["label"]
	if entry.get("mode_text"):
		text = entry["mode_text"].replace("{0}", text)
	if qty > 1:
		text = f"{text} x{qty}"
	if entry.get("instead_of"):
		text = _("{0} (instead of {1})").format(text, entry["instead_of"])
	return text


def _apply_free_choices(g, entries):
	"""The section's first N optional units are free: the cheapest ones lose their price."""
	free = cint(g.get("free_choices"))
	if free <= 0:
		return
	units = []
	for e in entries:
		if e["included"] or e["removed"] or not e.get("_affects") or flt(e["unit_price"]) <= 0:
			continue
		units += [(flt(e["unit_price"]), e)] * cint(e["qty"])
	units.sort(key=lambda u: u[0])
	for price, e in units[:free]:
		e["price"] = flt(e["price"] - price, 2)
		e["free_units"] = cint(e.get("free_units")) + 1


def resolve(item_code, item_group, selected, item_name=None, restaurant=None, price_list=None):
	"""
	Validate the options chosen by the client for an item.
	Returns (modifiers, amount): modifiers is the list stored on the order
	line (see the top of this file), amount the change of the unit price
	(for items priced from components: the whole unit price).
	"""
	chosen = _selected(selected)
	cat = Catalog(price_list)
	group_names = cat.groups_for(item_code)
	if not group_names:
		if chosen:
			frappe.throw(_("{0} has no options").format(frappe.bold(item_name or item_code)))
		return [], 0

	groups = cat.groups
	name = frappe.bold(item_name or item_code)
	modes = {m["name"]: m for m in modes_for(restaurant)} if any(g.get("use_modes") for g in groups.values()) else {}
	from_components = cat.from_components(item_code)
	used = set()

	def process(gname, parent=None):
		g = groups.get(gname)
		if not g or not g["options"]:
			return []
		picked = [o for o in g["options"] if (parent, o["id"]) in chosen]
		if len(picked) < g["min_select"]:
			frappe.throw(_("{0}: choose at least {1} in {2}").format(name, g["min_select"], frappe.bold(g["title"])),
			             title=_("Missing choice"))
		if g["max_select"] and len(picked) > g["max_select"]:
			frappe.throw(_("{0}: choose at most {1} in {2}").format(name, g["max_select"], frappe.bold(g["title"])))

		removed = [o for o in g["options"] if o["included"] and (parent, o["id"]) not in chosen]
		# one choice per section: what replaced the included option reads "Salad (instead of Fries)"
		swap = removed[0]["label"] if g["max_select"] == 1 and removed and picked else None

		entries = []
		for opt in g["options"]:
			key = (parent, opt["id"])
			mode = None
			if key in chosen:
				used.add(key)
				qty = chosen[key]["qty"]
				if qty > opt["max_qty"]:
					frappe.throw(_("{0}: {1} can be chosen at most {2} times").format(
						name, frappe.bold(opt["label"]), opt["max_qty"]))
				mode_name = chosen[key]["mode"]
				if mode_name:
					mode = modes.get(mode_name) if g.get("use_modes") else None
					if not mode:
						frappe.throw(_("{0}: {1} can't be ordered that way").format(name, frappe.bold(opt["label"])))
			elif opt["included"]:
				qty = 0
			else:
				continue
			share = flt(option_share(opt, qty, from_components, mode), 2)
			entry = {
				"group": gname,
				"group_title": g["title"],
				"option": opt["id"],
				"label": opt["label"],
				"qty": qty,
				"included": opt["included"],
				"removed": 1 if qty == 0 else 0,
				"unit_price": opt["price"],
				"price": share,
				"item": opt["item"],
				"ingredient_qty": opt["ingredient_qty"],
				"_affects": opt["affects_price"],
			}
			if opt.get("variant"):
				entry["variant"] = 1
			if parent:
				entry["parent"] = parent
			if mode:
				entry.update(mode=mode["name"], mode_label=mode["label"], mode_text=mode["kitchen_text"],
				             qty_factor=mode["qty_factor"])
			if swap and qty and not opt["included"]:
				entry["instead_of"] = swap
			if swap and qty == 0:
				entry["swapped"] = 1  # told by the option that replaced it
			entries.append(entry)
			# one level: what the chosen component asks for, right after it
			if qty and opt["nested"] and not parent:
				entry["_children"] = [c for sub in opt["nested"] for c in process(sub, opt["id"])]
		_apply_free_choices(g, entries)
		return entries

	modifiers, amount = [], 0
	for gname in group_names:
		for entry in process(gname):
			children = entry.pop("_children", [])
			entry["text"] = "" if entry.get("swapped") else entry_text(entry)
			kids = []
			for c in children:
				c["text"] = "" if c.get("swapped") else entry_text(c)
				if c["text"]:
					kids.append(c["text"])
			if kids:
				# "Coke: Large", "Burger: NO Tomato" (a component as it comes still tells what changed in it)
				entry["text"] = f"{entry['text'] or entry['label']}: {', '.join(kids)}"
			for e in [entry] + children:
				e.pop("_affects", None)
				if e.get("parent"):
					e["text"] = ""  # told by its parent
				modifiers.append(e)
				amount += e["price"]

	stray = [k for k in chosen if k not in used]
	if stray:
		frappe.throw(_("An option chosen for {0} is no longer available. Choose again.").format(name),
		             title=_("Option unavailable"))

	return modifiers, flt(amount, 2)


def parse(value):
	"""Ren Order Item.modifiers -> list"""
	if not value:
		return []
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except ValueError:
			return []
	return value if isinstance(value, list) else []


def texts(value):
	"""What to print / show for a line's options, in order (old lines: their labels)."""
	out = []
	for m in parse(value):
		text = m.get("text") if "text" in m else m.get("label")
		if text:
			out.append(text)
	return out


def summary(value):
	"""'Medium, NO Onions, Cheese x2' for tickets and invoices."""
	return ", ".join(texts(value))


def portions(entry):
	"""How many normal portions an entry ends up with: 0 removed, 0.5 light, 2 extra or x2..."""
	if entry.get("removed"):
		return 0
	factor = flt(entry.get("qty_factor")) if entry.get("qty_factor") not in (None, "") else 1
	return (cint(entry.get("qty")) or 1) * factor


# ─────────────────────────────────────────────
# Configuration checks (Item and Ren Option List)
# ─────────────────────────────────────────────

def _check_rows(rows, owner=None):
	for row in rows:
		row.role = row.role or "Optional"
		row.max_qty = max(cint(row.max_qty), 1)
		row.qty = flt(row.qty) or 1
		if row.role == "Included":
			row.preselected = 0  # included options always start checked
		if not row.item and not (row.label or "").strip():
			frappe.throw(_("Row {0}: choose a component or write a label").format(row.idx), title=_("Options"))
		if owner and row.item == owner:
			frappe.throw(_("Row {0}: an item can't be a component of itself").format(row.idx), title=_("Options"))
		if row.variant:
			if not row.item or frappe.db.get_value("Item", row.variant, "variant_of") != row.item:
				frappe.throw(_("Row {0}: {1} isn't a variant of {2}").format(
					row.idx, frappe.bold(row.variant), frappe.bold(row.item or "-")), title=_("Options"))


def _check_rules(title, rule, options):
	available = [o for o in options if not cint(o.unavailable)]
	min_s, max_s = cint(rule.min_select), cint(rule.max_select)
	if max_s and min_s > max_s:
		frappe.throw(_("{0}: minimum choices can't be greater than maximum choices").format(frappe.bold(title)))
	if min_s > len(available):
		frappe.throw(_("{0}: minimum choices ({1}) is greater than the available options ({2})").format(
			frappe.bold(title), min_s, len(available)))
	checked = [o for o in available if o.role == "Included" or cint(o.preselected)]
	if max_s and len(checked) > max_s:
		frappe.throw(_("{0}: more options come checked (included or preselected) than the maximum choices").format(
			frappe.bold(title)))
	labels = set()
	for o in options:
		key = (o.label or o.item or "").strip().lower()
		if key in labels:
			frappe.throw(_("{0}: option {1} is repeated").format(frappe.bold(title), frappe.bold(o.label or o.item)))
		labels.add(key)


def validate_option_list(doc):
	_check_rows(doc.options)
	_check_rules(doc.title, doc, doc.options)


def validate_item(doc, method=None):
	"""Item hook: the options and sections of the Restaurant tab."""
	if not doc.meta.has_field(OPTIONS_FIELD):
		return
	rows = doc.get(OPTIONS_FIELD) or []
	sections = doc.get(SECTIONS_FIELD) or []
	_check_rows(rows, doc.name)

	seen, lists = set(), set()
	for s in sections:
		s.section = (s.section or "").strip()
		if s.section in seen:
			frappe.throw(_("Section {0} is repeated").format(frappe.bold(section_title(s.section))), title=_("Sections"))
		seen.add(s.section)
		if s.option_list:
			if s.option_list in lists:
				frappe.throw(_("Ren Option List {0} is used twice").format(frappe.bold(s.option_list)), title=_("Sections"))
			lists.add(s.option_list)

	by_section = {}
	for r in rows:
		r.section = (r.section or "").strip()
		by_section.setdefault(r.section, []).append(r)
	for s in sections:
		opts = list(by_section.get(s.section, []))
		if s.option_list:
			opts += frappe.get_doc("Ren Option List", s.option_list).options
		if not opts:
			frappe.throw(_("Section {0} has no options: add some or choose a Ren Option List").format(
				frappe.bold(section_title(s.section))), title=_("Sections"))
		_check_rules(section_title(s.section), s, opts)
	for key, opts in by_section.items():
		if key not in seen:
			_check_rules(section_title(key), frappe._dict(min_select=0, max_select=0), opts)


def publish_change(doc=None, method=None):
	"""Open POS screens reload their options."""
	frappe.publish_realtime("modifiers_update", {"doctype": doc.doctype if doc else None}, after_commit=True)
