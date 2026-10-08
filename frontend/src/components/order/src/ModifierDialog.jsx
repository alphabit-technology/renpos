import { useMemo, useState } from "react";
import { X, Check, Minus, Plus } from "lucide-react";
import { flt, formatCurrency } from "../orderItems/calculator";
import {
  buildModifiers, defaultSelection, selectionFrom, sumModifiers, missingGroups, nestedKey, nestedOf, nestedDefaults,
} from "../modifierRules";

/**
 * ModifierDialog — choose the options of an item: temperature, sides,
 * extras, and the parts of a combo.
 *
 * Included options (part of the item) start checked; unchecking one removes
 * it ("NO Tomato"). Extras start unchecked (or preselected) and can be added,
 * some several times ("Cheese x2"). Groups with ingredient modes offer the
 * restaurant's modes on each checked option (Light, Extra, On the side…).
 * A component opens its own choices right under it (a drink asks for its
 * size, a burger inside a combo offers its options). The price updates as
 * you go; see ../modifierRules.js (the server applies the same rules).
 *
 * An item with sizes (ERPNext variants) shows them first; the line added is
 * the size chosen.
 *
 * Bottom sheet on phones, centered dialog on larger screens.
 *
 * Props:
 *   item      { item_name, price_list_rate }   base price without options
 *   fromComponents  the item's price is the sum of its options
 *   groups    the item's groups [{ name, title, min_select, max_select, free_choices, use_modes, options }]
 *   allGroups every group by name (for the groups options open)
 *   modes     the restaurant's ingredient modes
 *   initial   modifiers of the line being edited; what starts checked otherwise
 *   showQty   show a quantity stepper (adding a new line)
 *   variants  the item's sizes { attributes, variants: [{ item_code, values, label }] }
 *   resolveVariant (item_code) -> { item, groups, fromComponents } of a size
 *   onConfirm ({ modifiers, qty, item }) — modifiers in the order-line format;
 *             item = the size chosen (items with sizes)
 *   onClose
 */

function ruleText(g) {
  const min = g.min_select || 0;
  const max = g.max_select || 0;
  let text;
  if (min > 0 && max === min) text = min === 1 ? __("Required · choose 1") : __("Required · choose {0}", [min]);
  else if (min > 0) text = max ? __("Required · choose {0} to {1}", [min, max]) : __("Required · at least {0}", [min]);
  else if (max === 1) text = __("Optional · choose 1");
  else text = max ? __("Optional · up to {0}", [max]) : __("Optional");
  if (g.free_choices > 0) text += ` · ${__("{0} free", [g.free_choices])}`;
  return text;
}

function priceHint(o, fromComponents) {
  const price = flt(o.price);
  if (o.affects_price === 0 || !price) return o.included ? __("Included") : "";
  if (fromComponents) return formatCurrency(price);
  if (o.included) return __("Included");
  return `+${formatCurrency(price)}`;
}

function sameNames(a, b) {
  return a.length === b.length && a.every((g, i) => g.name === b[i].name);
}

export function ModifierDialog({
  item: baseItem, groups: baseGroups, allGroups = {}, modes = [], initial, fromComponents: baseFromComponents = false,
  showQty = false, variants = null, resolveVariant = null, onConfirm, onClose,
}) {
  const sizes = variants?.variants || [];
  const [variant, setVariant] = useState(() => sizes[0]?.item_code || null);
  const resolved = useMemo(
    () => (variant && resolveVariant ? resolveVariant(variant) : null),
    [variant, resolveVariant]
  );
  const item = resolved?.item || baseItem;
  const groups = resolved?.groups || baseGroups;
  const fromComponents = resolved ? !!resolved.fromComponents : baseFromComponents;

  const [selected, setSelected] = useState(() => (
    initial ? selectionFrom(groups, initial, allGroups) : defaultSelection(groups, allGroups)
  ));
  const [qty, setQty] = useState(1);
  const [touched, setTouched] = useState(false);

  const chooseVariant = (code) => {
    if (code === variant) return;
    const next = resolveVariant?.(code);
    // another size with other options starts over; same options keep what was chosen
    if (next && !sameNames(next.groups || [], groups)) setSelected(defaultSelection(next.groups || [], allGroups));
    setVariant(code);
  };

  // a size per attribute (Size, Crust…): the variant with those values
  const attributes = variants?.attributes || [];
  const current = sizes.find((v) => v.item_code === variant);
  const pickValue = (attr, value) => {
    const want = { ...(current?.values || {}), [attr]: value };
    const exact = sizes.find((v) => attributes.every((a) => (v.values || {})[a] === want[a]));
    const any = sizes.find((v) => (v.values || {})[attr] === value);
    if (exact || any) chooseVariant((exact || any).item_code);
  };

  // checking an option starts the groups it opens with their defaults; unchecking drops them
  const withNested = (next, o, on) => {
    const subs = nestedOf(o, allGroups);
    if (!subs.length) return next;
    if (on) {
      const defaults = nestedDefaults(o, allGroups);
      const out = { ...next };
      for (const k of Object.keys(defaults)) out[k] = next[k] || defaults[k];
      return out;
    }
    const copy = { ...next };
    for (const sub of subs) delete copy[nestedKey(o.id, sub.name)];
    return copy;
  };

  const toggle = (g, gkey, o) => {
    setSelected((prev) => {
      const cur = { ...(prev[gkey] || {}) };
      if (cur[o.id]) {
        delete cur[o.id];
        return withNested({ ...prev, [gkey]: cur }, o, false);
      }
      if (g.max_select === 1) {
        let next = { ...prev, [gkey]: { [o.id]: { qty: 1, mode: null } } };
        for (const other of g.options) if (other.id !== o.id && cur[other.id]) next = withNested(next, other, false);
        return withNested(next, o, true);
      }
      if (g.max_select && Object.keys(cur).length >= g.max_select) return prev; // full
      cur[o.id] = { qty: 1, mode: null };
      return withNested({ ...prev, [gkey]: cur }, o, true);
    });
  };

  const setOption = (gkey, o, patch) => {
    setSelected((prev) => {
      const cur = { ...(prev[gkey] || {}) };
      if (!cur[o.id]) return prev;
      const next = { ...cur[o.id], ...patch };
      if (next.qty <= 0) delete cur[o.id];
      else cur[o.id] = { ...next, qty: Math.min(next.qty, o.max_qty || 1) };
      return { ...prev, [gkey]: cur };
    });
  };

  const missing = useMemo(() => missingGroups(groups, selected, allGroups), [groups, selected, allGroups]);
  const modifiers = useMemo(
    () => buildModifiers(groups, selected, fromComponents, allGroups, modes),
    [groups, selected, fromComponents, allGroups, modes]
  );
  const base = fromComponents ? 0 : flt(item?.price_list_rate);
  const unit = Math.max(base + sumModifiers(modifiers), 0);

  const confirm = () => {
    setTouched(true);
    if (missing.length) {
      document.getElementById(`mod-group-${missing[0]}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    onConfirm({ modifiers, qty, item: resolved ? item : undefined });
  };

  const renderGroup = (g, gkey, parent) => {
    const chosen = selected[gkey] || {};
    const isMissing = touched && missing.includes(gkey);
    const full = g.max_select > 1 && Object.keys(chosen).length >= g.max_select;
    return (
      <section key={gkey} id={`mod-group-${gkey}`}
        className={parent ? "mt-2 ml-4 pl-3 border-l-2 border-blue-500/40" : ""}>
        <div className="flex items-baseline justify-between gap-2 mb-2">
          <h3 className={`${parent ? "text-sm" : "text-[15px]"} font-semibold m-0`}>{g.title}</h3>
          <span className={`text-xs ${isMissing ? "text-destructive font-semibold" : "text-muted-foreground"}`}>
            {ruleText(g)}
          </span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {g.options.map((o) => {
            const c = chosen[o.id];
            const q = c?.qty || 0;
            const on = q > 0;
            const removed = !on && !!o.included;
            const disabled = !on && full;
            const multi = on && (o.max_qty || 1) > 1;
            const hint = priceHint(o, fromComponents);
            const showModes = !!(on && g.use_modes && modes.length > 0);
            const subs = on && !parent ? nestedOf(o, allGroups) : [];
            return (
              <div key={o.id} className={subs.length || showModes ? "sm:col-span-2" : ""}>
                <div
                  className={`min-h-[48px] rounded-xl border flex flex-col transition-colors ${disabled ? "opacity-40" : ""} ${
                    on
                      ? "border-blue-500 bg-blue-500/15 text-card-foreground"
                      : removed
                        ? "border-dashed border-destructive/50 bg-destructive/5"
                        : isMissing
                          ? "border-destructive/50 bg-transparent"
                          : "border-border bg-muted/20 hover:bg-muted/50"
                  }`}
                >
                  <div className="flex items-center">
                    <button
                      onClick={() => toggle(g, gkey, o)}
                      disabled={disabled}
                      className="flex-1 min-w-0 self-stretch min-h-[48px] px-3 py-2 flex items-center gap-3 text-left"
                    >
                      <span className={`w-5 h-5 shrink-0 flex items-center justify-center border ${
                        g.max_select === 1 ? "rounded-full" : "rounded-md"
                      } ${on ? "bg-blue-500 border-blue-500 text-white" : "border-muted-foreground/40"}`}>
                        {on && <Check size={13} strokeWidth={3} />}
                      </span>
                      <span className="flex-1 min-w-0">
                        <span className={`block text-sm font-medium truncate ${removed ? "line-through text-muted-foreground" : ""}`}>
                          {o.label}
                        </span>
                        {removed && (
                          <span className="block text-[11px] font-semibold text-destructive">
                            {__("Removed")}
                            {!fromComponents && o.affects_price !== 0 && flt(o.price) > 0 && ` · −${formatCurrency(o.price)}`}
                          </span>
                        )}
                      </span>
                      {!multi && hint && (
                        <span className={`text-xs tabular-nums shrink-0 ${o.included ? "text-emerald-400" : "text-muted-foreground"}`}>
                          {hint}
                        </span>
                      )}
                    </button>
                    {multi && (
                      <div className="flex items-center gap-1 pr-2 shrink-0">
                        <button onClick={() => setOption(gkey, o, { qty: q - 1 })} className="w-8 h-8 rounded-lg border border-border flex items-center justify-center active:bg-muted" aria-label={__("Less")}>
                          <Minus size={14} />
                        </button>
                        <span className="w-5 text-center text-sm font-semibold tabular-nums">{q}</span>
                        <button onClick={() => setOption(gkey, o, { qty: q + 1 })} disabled={q >= (o.max_qty || 1)}
                          className="w-8 h-8 rounded-lg border border-border flex items-center justify-center active:bg-muted disabled:opacity-30" aria-label={__("More")}>
                          <Plus size={14} />
                        </button>
                      </div>
                    )}
                  </div>
                  {showModes && (
                    <div className="flex flex-wrap gap-1.5 px-3 pb-2 -mt-1">
                      {[{ name: null, label: __("Normal"), price_factor: 0 }, ...modes].map((m) => {
                        const active = (c.mode || null) === m.name;
                        const extra = flt(m.price_factor) * flt(o.price);
                        return (
                          <button key={m.name || "normal"} onClick={() => setOption(gkey, o, { mode: m.name })}
                            className={`h-8 px-3 rounded-full text-xs font-semibold border transition-colors ${
                              active ? "bg-foreground text-background border-foreground" : "border-border text-muted-foreground hover:text-foreground"
                            }`}>
                            {m.label}{extra > 0 && o.affects_price !== 0 ? ` +${formatCurrency(extra)}` : ""}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
                {subs.map((sub) => renderGroup(sub, nestedKey(o.id, sub.name), o.id))}
              </div>
            );
          })}
        </div>
      </section>
    );
  };

  return (
    <div className="fixed inset-0 z-[1050] flex items-end sm:items-center justify-center bg-black/60 animate-fade-in" onClick={onClose}>
      <div
        className="w-full sm:max-w-lg max-h-[92vh] flex flex-col bg-card text-card-foreground border border-border rounded-t-3xl sm:rounded-2xl shadow-2xl animate-slide-up"
        onClick={(e) => e.stopPropagation()}
      >
        {/* header */}
        <div className="shrink-0 flex items-start gap-3 px-5 pt-4 pb-3 border-b border-border">
          <div className="flex-1 min-w-0">
            <div className="text-lg font-semibold leading-tight truncate">{item?.item_name || baseItem?.item_name}</div>
            <div className="text-sm text-muted-foreground tabular-nums">
              {fromComponents ? __("Price from what you choose") : formatCurrency(item?.price_list_rate)}
            </div>
          </div>
          <button onClick={onClose} className="w-9 h-9 -mr-2 flex items-center justify-center rounded-xl text-muted-foreground hover:bg-muted" aria-label={__("Close")}>
            <X size={20} />
          </button>
        </div>

        {/* sizes, then the groups */}
        <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-5 py-3 space-y-5">
          {sizes.length > 0 && attributes.map((attr) => {
            const values = [...new Set(sizes.map((v) => (v.values || {})[attr]).filter(Boolean))];
            const single = attributes.length === 1;
            return (
              <section key={`attr-${attr}`}>
                <div className="flex items-baseline justify-between gap-2 mb-2">
                  <h3 className="text-[15px] font-semibold m-0">{__(attr)}</h3>
                  <span className="text-xs text-muted-foreground">{__("Required · choose 1")}</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {values.map((value) => {
                    const active = (current?.values || {})[attr] === value;
                    const size = single ? sizes.find((v) => (v.values || {})[attr] === value) : null;
                    const price = size ? resolveVariant?.(size.item_code)?.item?.price_list_rate : null;
                    return (
                      <button key={value} onClick={() => pickValue(attr, value)}
                        className={`min-h-[48px] min-w-[84px] px-4 rounded-xl border flex flex-col items-center justify-center transition-colors ${
                          active ? "border-blue-500 bg-blue-500/15" : "border-border bg-muted/20 hover:bg-muted/50"
                        }`}>
                        <span className="text-sm font-semibold">{value}</span>
                        {price != null && <span className="text-[11px] text-muted-foreground tabular-nums">{formatCurrency(price)}</span>}
                      </button>
                    );
                  })}
                </div>
              </section>
            );
          })}
          {groups.map((g) => renderGroup(g, g.name, null))}
        </div>

        {/* footer */}
        <div className="shrink-0 flex items-center gap-3 px-5 pt-3 border-t border-border"
             style={{ paddingBottom: "max(0.75rem, env(safe-area-inset-bottom))" }}>
          {showQty && (
            <div className="flex items-center gap-1">
              <button onClick={() => setQty((v) => Math.max(1, v - 1))} className="w-11 h-11 rounded-xl border border-border flex items-center justify-center active:bg-muted" aria-label={__("Less")}>
                <Minus size={18} />
              </button>
              <span className="w-8 text-center text-lg font-semibold tabular-nums">{qty}</span>
              <button onClick={() => setQty((v) => v + 1)} className="w-11 h-11 rounded-xl border border-border flex items-center justify-center active:bg-muted" aria-label={__("More")}>
                <Plus size={18} />
              </button>
            </div>
          )}
          <button
            onClick={confirm}
            className={`flex-1 min-h-[48px] rounded-2xl px-4 flex items-center justify-between font-semibold text-white transition-colors ${
              missing.length ? "bg-blue-600/50" : "bg-blue-600 active:bg-blue-700"
            }`}
          >
            <span>{initial ? __("Update") : __("Add")}</span>
            <span className="tabular-nums">{formatCurrency(unit * (showQty ? qty : 1))}</span>
          </button>
        </div>
      </div>
    </div>
  );
}

export default ModifierDialog;
