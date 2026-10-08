import { flt } from "./orderItems/calculator";

/**
 * Item options and combos — the same rules as the server
 * (renpos/api/modifiers.py), so the price and the texts are
 * right before the server answers. The server recomputes everything.
 *
 * option: { id, label, price, item, ingredient_qty, included, is_default,
 *           affects_price, max_qty, nested, variant }
 *   included  part of the item: starts checked, can be removed ("NO Tomato")
 *   optional  starts unchecked (or preselected), up to max_qty ("Cheese x2")
 *   nested    groups the option opens when chosen (one level): the size of a
 *             drink, the options of a burger inside a combo
 * group:  { name, title, min_select, max_select, free_choices, use_modes, options }
 *         (a section of the item; "variants" = the sizes of a component)
 * mode:   { name, label, kitchen_text, price_factor, qty_factor }  (Light, Extra…)
 *
 * Selection: { [groupKey]: { [optionId]: { qty, mode } } }, groupKey = the
 * group's name, or "parentOptionId>groupName" for a group an option opens.
 *
 * Unit price:
 *   fixed price            item price + changes of the options that change the price
 *   price from components  the sum of the options chosen
 *   + a mode's price factor x price, - the group's free choices (cheapest extras)
 */

export const nestedKey = (parentId, groupName) => `${parentId}>${groupName}`;

export function optionShare(o, qty, fromComponents, mode) {
  if (o.affects_price === 0) return 0;
  const price = flt(o.price);
  const extra = mode && qty ? flt(mode.price_factor) * price * qty : 0;
  if (fromComponents) return price * qty + extra;
  if (o.included) return price * (qty - 1) + extra;
  return price * qty + extra;
}

function groupDefaults(g) {
  const out = {};
  for (const o of g.options) if (o.included || o.is_default) out[o.id] = { qty: 1, mode: null };
  return out;
}

/** the groups an option opens */
export const nestedOf = (o, allGroups = {}) => (o.nested || []).map((n) => allGroups[n]).filter((g) => g?.options?.length);

/** an option was checked: the groups it opens start with their defaults */
export function nestedDefaults(o, allGroups = {}) {
  const out = {};
  for (const sub of nestedOf(o, allGroups)) out[nestedKey(o.id, sub.name)] = groupDefaults(sub);
  return out;
}

/** what starts checked (and the defaults of what the checked options open) */
export function defaultSelection(groups, allGroups = {}) {
  let sel = {};
  for (const g of groups) {
    sel[g.name] = groupDefaults(g);
    for (const o of g.options) if (sel[g.name][o.id]) sel = { ...sel, ...nestedDefaults(o, allGroups) };
  }
  return sel;
}

/** a line's saved options back into a selection */
export function selectionFrom(groups, modifiers, allGroups = {}) {
  const sel = {};
  const saved = {};
  for (const m of modifiers || []) {
    if (m.removed) continue;
    const key = `${m.parent || ""}|${m.option}`;
    saved[key] = { qty: Number(m.qty) || 1, mode: m.mode || null };
  }
  const fill = (g, parent) => {
    const out = {};
    for (const o of g.options) {
      const s = saved[`${parent || ""}|${o.id}`];
      if (s) out[o.id] = { qty: Math.min(s.qty, o.max_qty || 1), mode: s.mode };
    }
    return out;
  };
  for (const g of groups) {
    sel[g.name] = fill(g, null);
    for (const o of g.options) {
      if (!sel[g.name][o.id]) continue;
      for (const sub of nestedOf(o, allGroups)) sel[nestedKey(o.id, sub.name)] = fill(sub, o.id);
    }
  }
  return sel;
}

export function entryText(e) {
  if (e.removed) return __("NO {0}", [e.label]);
  const qty = Number(e.qty) || 1;
  if (e.included && qty === 1 && !e.instead_of && !e.mode) return "";
  let text = e.label;
  if (e.mode_text) text = e.mode_text.replace("{0}", text);
  if (qty > 1) text = `${text} x${qty}`;
  if (e.instead_of) text = __("{0} (instead of {1})", [text, e.instead_of]);
  return text;
}

function applyFree(g, entries) {
  const free = Number(g.free_choices) || 0;
  if (free <= 0) return;
  const units = [];
  for (const e of entries) {
    if (e.included || e.removed || !e._affects || flt(e.unit_price) <= 0) continue;
    for (let i = 0; i < e.qty; i++) units.push(e);
  }
  units.sort((a, b) => flt(a.unit_price) - flt(b.unit_price));
  for (const e of units.slice(0, free)) {
    e.price = flt(e.price - flt(e.unit_price), 2);
    e.free_units = (e.free_units || 0) + 1;
  }
}

/** selection -> order-line entries (chosen options and included ones removed) */
export function buildModifiers(groups, selection, fromComponents, allGroups = {}, modes = []) {
  const modeBy = Object.fromEntries((modes || []).map((m) => [m.name, m]));

  const process = (g, parent) => {
    const chosen = selection[parent ? nestedKey(parent, g.name) : g.name] || {};
    const removed = g.options.filter((o) => o.included && !chosen[o.id]);
    const picked = g.options.filter((o) => chosen[o.id]);
    const swap = g.max_select === 1 && removed.length && picked.length ? removed[0].label : null;
    const entries = [];
    for (const o of g.options) {
      const c = chosen[o.id];
      let qty;
      if (c) qty = c.qty;
      else if (o.included) qty = 0;
      else continue;
      const mode = c && c.mode && g.use_modes ? modeBy[c.mode] : null;
      const entry = {
        group: g.name,
        group_title: g.title,
        option: o.id,
        label: o.label,
        qty,
        included: o.included ? 1 : 0,
        removed: qty === 0 ? 1 : 0,
        unit_price: flt(o.price),
        price: flt(optionShare(o, qty, fromComponents, mode), 2),
        item: o.item || null,
        ingredient_qty: flt(o.ingredient_qty) || 1,
        _affects: o.affects_price === 0 ? 0 : 1,
      };
      if (o.variant) entry.variant = 1;
      if (parent) entry.parent = parent;
      if (mode) Object.assign(entry, { mode: mode.name, mode_label: mode.label, mode_text: mode.kitchen_text, qty_factor: mode.qty_factor });
      if (swap && qty && !o.included) entry.instead_of = swap;
      if (swap && qty === 0) entry.swapped = 1;
      entries.push(entry);
      if (qty && !parent) {
        const subs = nestedOf(o, allGroups);
        if (subs.length) entry._children = subs.flatMap((sub) => process(sub, o.id));
      }
    }
    applyFree(g, entries);
    return entries;
  };

  const out = [];
  for (const g of groups) {
    for (const entry of process(g, null)) {
      const children = entry._children || [];
      delete entry._children;
      entry.text = entry.swapped ? "" : entryText(entry);
      const kids = children.map((c) => (c.swapped ? "" : entryText(c))).filter(Boolean);
      // "Coke: Large", "Burger: NO Tomato"
      if (kids.length) entry.text = `${entry.text || entry.label}: ${kids.join(", ")}`;
      for (const e of [entry, ...children]) {
        delete e._affects;
        if (e.parent) e.text = "";
        out.push(e);
      }
    }
  }
  return out;
}

/** groups (top level and nested under a chosen option) still missing a required choice */
export function missingGroups(groups, selection, allGroups = {}) {
  const out = [];
  for (const g of groups) {
    const chosen = selection[g.name] || {};
    if (Object.keys(chosen).length < (g.min_select || 0)) out.push(g.name);
    for (const o of g.options) {
      if (!chosen[o.id]) continue;
      for (const sub of nestedOf(o, allGroups)) {
        const key = nestedKey(o.id, sub.name);
        if (Object.keys(selection[key] || {}).length < (sub.min_select || 0)) out.push(key);
      }
    }
  }
  return out;
}

/** texts to show for a line (lines saved before combos: their labels) */
export function modifierTexts(mods) {
  return (mods || [])
    .map((m) => ("text" in m ? m.text : m.label))
    .filter(Boolean);
}

/** order-independent key of the chosen options, to merge identical lines */
export function modifiersKey(mods) {
  return (mods || [])
    .filter((m) => !m.removed)
    .map((m) => `${m.parent || ""}>${m.option}:${Number(m.qty) || 1}:${m.mode || ""}`)
    .sort()
    .join("|");
}

export function sumModifiers(mods) {
  return (mods || []).reduce((s, m) => s + flt(m.price), 0);
}
