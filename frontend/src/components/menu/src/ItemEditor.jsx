import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  X, Loader2, Plus, Trash2, ImagePlus, Search, Layers, Type, ChevronUp, ChevronDown, Eye,
} from "lucide-react";
import { callWithApproval } from "@/utils/approval";
import { ModifierDialog } from "@c/order/src/ModifierDialog";
import { modifierTexts, sumModifiers } from "@c/order/modifierRules";

/**
 * ItemEditor — edit (or create) an item from the Menu Manager.
 *
 * It edits the ERPNext Item itself (api/item_editor.py): name, group,
 * photo, description, tags, the price on the restaurant's price list, and
 * the Restaurant tab (sections, options, combo settings). With a menu
 * open it also says whether the item is on it and at what menu price.
 * The desk form shows exactly the same data.
 *
 * Tabs: Basics · Sizes (ERPNext variants) · Options & combo · Recipe (BOM).
 * "Preview" shows the dialog the waiter will get, built by the server from
 * the unsaved data (nothing is kept).
 *
 * Props: itemCode (null = new item), menu, onClose, onSaved(item)
 */

const API = "renpos.api.item_editor";
const INGREDIENTS = "";

const num = (v) => (v === "" || v == null ? "" : Number(v));
const cleanNum = (v, integer) => {
  let out = integer ? String(v).replace(/\D/g, "") : String(v).replace(/[^\d.]/g, "").replace(/(\..*)\./g, "$1");
  return out;
};

function Field({ label, hint, children, className = "" }) {
  return (
    <label className={`block ${className}`}>
      <span className="block text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-1">{label}</span>
      {children}
      {hint && <span className="block text-[11px] text-muted-foreground mt-1">{hint}</span>}
    </label>
  );
}

const input = "w-full h-10 px-3 rounded-lg bg-background border border-border text-sm outline-none focus:border-blue-500";

function Toggle({ checked, onChange, label, hint }) {
  return (
    <button type="button" onClick={() => onChange(!checked)} className="w-full flex items-start gap-3 text-left py-1.5">
      <span className={`mt-0.5 shrink-0 w-9 h-5 rounded-full relative transition-colors ${checked ? "bg-blue-600" : "bg-muted"}`}>
        <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all ${checked ? "left-[18px]" : "left-0.5"}`} />
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-medium">{label}</span>
        {hint && <span className="block text-xs text-muted-foreground">{hint}</span>}
      </span>
    </button>
  );
}

function NumberInput({ value, onChange, integer = false, placeholder, className = "", small = false }) {
  const base = small
    ? "h-8 px-2 rounded-lg bg-background border border-border text-sm outline-none focus:border-blue-500"
    : input;
  return (
    <input
      type="text" inputMode={integer ? "numeric" : "decimal"} value={value ?? ""} placeholder={placeholder}
      onChange={(e) => onChange(cleanNum(e.target.value, integer))}
      className={`${base} tabular-nums ${className}`}
    />
  );
}

// ─────────────────────────────────────────────
// Item search (component / option)
// ─────────────────────────────────────────────

function ItemPicker({ onPick, onClose, method = "search_items", placeholder }) {
  const [txt, setTxt] = useState("");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    let alive = true;
    const t = setTimeout(() => {
      setLoading(true);
      callWithApproval(`${API}.${method}`, { txt, limit: 25 })
        .then((r) => alive && setRows(r || []))
        .finally(() => alive && setLoading(false));
    }, 200);
    return () => { alive = false; clearTimeout(t); };
  }, [txt, method]);
  return (
    <div className="rounded-xl border border-blue-500/50 bg-background p-2 space-y-2">
      <div className="relative">
        <Search size={15} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <input autoFocus value={txt} onChange={(e) => setTxt(e.target.value)} placeholder={placeholder || __("Search items or ingredients")}
          className={`${input} pl-8`} onKeyDown={(e) => e.key === "Escape" && onClose()} />
      </div>
      <div className="max-h-56 overflow-y-auto divide-y divide-border">
        {loading && !rows.length && <div className="py-3 text-center text-xs text-muted-foreground"><Loader2 size={14} className="inline animate-spin" /></div>}
        {rows.map((r) => (
          <button key={r.item_code} type="button" onClick={() => onPick(r)}
            className="w-full flex items-center gap-2 px-2 py-2 text-left hover:bg-muted/60 rounded-md">
            <span className="flex-1 min-w-0">
              <span className="block text-sm font-medium truncate">{r.item_name}</span>
              <span className="block text-[11px] text-muted-foreground truncate">{r.item_group}{r.has_variants ? ` · ${__("has sizes")}` : ""}{r.uom ? ` · ${r.uom}` : ""}</span>
            </span>
            {method === "search_items" && (
              <span className={`text-[10px] px-1.5 py-0.5 rounded ${r.is_sales_item ? "bg-emerald-500/15 text-emerald-400" : "bg-muted text-muted-foreground"}`}>
                {r.is_sales_item ? __("Menu item") : __("Ingredient")}
              </span>
            )}
          </button>
        ))}
      </div>
      <div className="flex justify-end">
        <button type="button" onClick={onClose} className="text-xs px-3 py-1.5 rounded-lg hover:bg-muted text-muted-foreground">{__("Close")}</button>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// One section of options
// ─────────────────────────────────────────────

function OptionRow({ o, fromComponents, onChange, onRemove, onMove }) {
  const included = o.role === "Included";
  return (
    <div className="grid grid-cols-[auto_1fr_auto] gap-2 items-start py-2">
      <div className="flex flex-col pt-1">
        <button type="button" onClick={() => onMove(-1)} className="text-muted-foreground hover:text-foreground" aria-label={__("Up")}><ChevronUp size={14} /></button>
        <button type="button" onClick={() => onMove(1)} className="text-muted-foreground hover:text-foreground" aria-label={__("Down")}><ChevronDown size={14} /></button>
      </div>
      <div className="min-w-0 space-y-2">
        <div className="flex items-center gap-2">
          {o.item ? (
            <span className="flex-1 min-w-0">
              <input value={o.label || ""} onChange={(e) => onChange({ label: e.target.value })} placeholder={o.item_name || o.item}
                className={`${input} h-9`} />
              <span className="block text-[10px] text-muted-foreground mt-0.5 truncate">{__("Item")}: {o.item}</span>
            </span>
          ) : (
            <input value={o.label || ""} onChange={(e) => onChange({ label: e.target.value })} placeholder={__("Option text")}
              className={`${input} h-9 flex-1`} />
          )}
          <div className="flex rounded-lg border border-border overflow-hidden shrink-0 text-xs font-semibold">
            {["Included", "Optional"].map((r) => (
              <button key={r} type="button" onClick={() => onChange({ role: r })}
                className={`px-2.5 h-9 ${o.role === r ? "bg-blue-600 text-white" : "text-muted-foreground hover:bg-muted"}`}>
                {r === "Included" ? __("Included") : __("Extra")}
              </button>
            ))}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs">
          <label className="flex items-center gap-1.5">
            <span className="text-muted-foreground whitespace-nowrap">{fromComponents ? __("Price") : included ? __("Price if removed") : __("Extra price")}</span>
            <NumberInput small value={o.price ?? ""} onChange={(v) => onChange({ price: num(v) })} placeholder="0.00" className="w-20" />
          </label>
          <label className="flex items-center gap-1.5">
            <span className="text-muted-foreground whitespace-nowrap">{__("Up to")}</span>
            <NumberInput small integer value={o.max_qty ?? 1} onChange={(v) => onChange({ max_qty: num(v) })} className="w-14" />
          </label>
          {!included && (
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input type="checkbox" checked={!!o.preselected} onChange={(e) => onChange({ preselected: e.target.checked ? 1 : 0 })} />
              <span>{__("Checked by default")}</span>
            </label>
          )}
          <label className="flex items-center gap-1.5 cursor-pointer">
            <input type="checkbox" checked={!!o.unavailable} onChange={(e) => onChange({ unavailable: e.target.checked ? 1 : 0 })} />
            <span>{__("Unavailable")}</span>
          </label>
        </div>
      </div>
      <button type="button" onClick={onRemove} className="mt-1 w-8 h-8 rounded-lg text-destructive/70 hover:text-destructive hover:bg-destructive/10 flex items-center justify-center" aria-label={__("Remove")}>
        <Trash2 size={15} />
      </button>
    </div>
  );
}

function SectionCard({ section, options, lookups, fromComponents, onChange, onRemove, onOption, onAddOption, onRemoveOption, onMoveOption }) {
  const [picking, setPicking] = useState(false);
  const name = section.section;
  return (
    <div className="rounded-xl border border-border bg-muted/10">
      <div className="p-3 border-b border-border space-y-3">
        <div className="flex items-center gap-2">
          <input value={name} onChange={(e) => onChange({ section: e.target.value })}
            placeholder={__("Ingredients")} className={`${input} font-semibold flex-1`} />
          <button type="button" onClick={onRemove} className="w-10 h-10 rounded-lg text-destructive/70 hover:text-destructive hover:bg-destructive/10 flex items-center justify-center shrink-0" aria-label={__("Remove section")}>
            <Trash2 size={16} />
          </button>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <Field label={__("Choose at least")}><NumberInput integer value={section.min_select ?? 0} onChange={(v) => onChange({ min_select: num(v) })} /></Field>
          <Field label={__("At most")} hint={__("0 = no limit")}><NumberInput integer value={section.max_select ?? 0} onChange={(v) => onChange({ max_select: num(v) })} /></Field>
          <Field label={__("Free choices")}><NumberInput integer value={section.free_choices ?? 0} onChange={(v) => onChange({ free_choices: num(v) })} /></Field>
        </div>
        <div className="grid grid-cols-2 gap-2 items-end">
          <Field label={__("Shared option list")} hint={__("Its options are added to this section")}>
            <select value={section.option_list || ""} onChange={(e) => onChange({ option_list: e.target.value })} className={input}>
              <option value="">{__("None")}</option>
              {(lookups?.option_lists || []).map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
          </Field>
          <div className="text-xs space-y-1.5 pb-1">
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input type="checkbox" checked={!!section.use_modes} onChange={(e) => onChange({ use_modes: e.target.checked ? 1 : 0 })} />
              {__("Light / Extra / On the side")}
            </label>
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input type="checkbox" checked={!!section.price_by_size} onChange={(e) => onChange({ price_by_size: e.target.checked ? 1 : 0 })} />
              {__("Prices change with the size")}
            </label>
          </div>
        </div>
      </div>
      <div className="px-3 divide-y divide-border">
        {options.length === 0 && !section.option_list && (
          <p className="py-3 text-xs text-amber-400">{__("Add options, or choose a shared option list.")}</p>
        )}
        {options.map(({ o, index }) => (
          <OptionRow key={index} o={o} fromComponents={fromComponents}
            onChange={(patch) => onOption(index, patch)} onRemove={() => onRemoveOption(index)}
            onMove={(d) => onMoveOption(index, d)} />
        ))}
      </div>
      <div className="p-3 pt-2 space-y-2">
        {picking ? (
          <ItemPicker onClose={() => setPicking(false)} onPick={(r) => {
            onAddOption({ item: r.item_code, item_name: r.item_name, label: "", role: "Included", max_qty: 1 });
            setPicking(false);
          }} />
        ) : (
          <div className="flex gap-2">
            <button type="button" onClick={() => setPicking(true)} className="flex-1 h-9 rounded-lg border border-dashed border-border text-xs font-semibold text-muted-foreground hover:text-foreground hover:bg-muted/50 flex items-center justify-center gap-1.5">
              <Layers size={14} /> {__("Add item / ingredient")}
            </button>
            <button type="button" onClick={() => onAddOption({ label: "", role: "Optional", max_qty: 1 })} className="flex-1 h-9 rounded-lg border border-dashed border-border text-xs font-semibold text-muted-foreground hover:text-foreground hover:bg-muted/50 flex items-center justify-center gap-1.5">
              <Type size={14} /> {__("Add text option")}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// Editor
// ─────────────────────────────────────────────

export function ItemEditor({ itemCode, menu, onClose, onSaved }) {
  const isNew = !itemCode;
  const [tab, setTab] = useState("basics");
  const [lookups, setLookups] = useState(null);
  const [data, setData] = useState(null);       // the item being edited
  const [menuState, setMenuState] = useState(null);
  const [meta, setMeta] = useState({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [sizes, setSizes] = useState(null);      // {attribute, values: [{value, price, enabled, item_code}]}
  const [recipe, setRecipe] = useState(null);    // {lines, inherited, bom}
  const [recipeTouched, setRecipeTouched] = useState(false);
  const [sold, setSold] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [preview, setPreview] = useState(null);  // what the POS would get
  const [picked, setPicked] = useState(null);    // what was chosen in the preview
  const [ingPicking, setIngPicking] = useState(false);
  const sectionKeys = useRef(0);

  useEffect(() => {
    let alive = true;
    callWithApproval(`${API}.get_lookups`).then((r) => alive && setLookups(r)).catch(() => {});
    if (isNew) {
      setData({ item_name: "", item_group: "", description: "", image: "", tags: [], price: "", price_from_components: 0,
                route_components: 0, sections: [], options: [], is_stock_item: 0 });
      setMenuState(menu ? { in_menu: true, rate: "" } : null);
      setRecipe({ lines: [], inherited: false, bom: null });
    } else {
      callWithApproval(`${API}.get_item`, { item_code: itemCode, menu }).then((r) => {
        if (!alive) return;
        setData(withKeys(r.item));
        setMenuState(r.menu ? { in_menu: r.menu.in_menu, rate: r.menu.rate || "" } : null);
        setMeta({ price_list: r.price_list });
        setSizes(r.sizes || null);
        setRecipe(r.recipe || { lines: [] });
        setSold(!!r.sold);
      }).catch(() => alive && onClose());
    }
    return () => { alive = false; };
  }, [itemCode, menu]); // eslint-disable-line react-hooks/exhaustive-deps

  // every section gets a stable key; options keep pointing at the section by name
  const withKeys = (item) => {
    const names = new Set((item.sections || []).map((s) => s.section || INGREDIENTS));
    const sections = (item.sections || []).map((s) => ({ ...s, section: s.section || INGREDIENTS, _key: ++sectionKeys.current }));
    // options in a section that has no row of its own still get a card
    for (const o of item.options || []) {
      const n = o.section || INGREDIENTS;
      if (!names.has(n)) { names.add(n); sections.push({ section: n, min_select: 0, max_select: 0, _key: ++sectionKeys.current }); }
    }
    return { ...item, sections, options: (item.options || []).map((o) => ({ ...o, section: o.section || INGREDIENTS })) };
  };

  const set = (patch) => setData((d) => ({ ...d, ...patch }));

  const updateSection = (key, patch) => setData((d) => {
    const old = d.sections.find((s) => s._key === key);
    const sections = d.sections.map((s) => (s._key === key ? { ...s, ...patch } : s));
    // renaming a section carries its options along
    const options = "section" in patch
      ? d.options.map((o) => (o.section === old.section ? { ...o, section: patch.section } : o))
      : d.options;
    return { ...d, sections, options };
  });
  const removeSection = (key) => setData((d) => {
    const old = d.sections.find((s) => s._key === key);
    return { ...d, sections: d.sections.filter((s) => s._key !== key), options: d.options.filter((o) => o.section !== old.section) };
  });
  const addSection = () => setData((d) => {
    const taken = new Set(d.sections.map((s) => s.section));
    let n = 1;
    let name = __("Choice");
    while (taken.has(name)) name = `${__("Choice")} ${++n}`;
    return { ...d, sections: [...d.sections, { section: name, min_select: 1, max_select: 1, _key: ++sectionKeys.current }] };
  });
  const updateOption = (i, patch) => setData((d) => ({ ...d, options: d.options.map((o, j) => (j === i ? { ...o, ...patch } : o)) }));
  const removeOption = (i) => setData((d) => ({ ...d, options: d.options.filter((_, j) => j !== i) }));
  const addOption = (section, o) => setData((d) => ({ ...d, options: [...d.options, { ...o, section }] }));
  const moveOption = (i, dir) => setData((d) => {
    const opts = [...d.options];
    const sec = opts[i].section;
    let j = i + dir;
    while (j >= 0 && j < opts.length && opts[j].section !== sec) j += dir;
    if (j < 0 || j >= opts.length) return d;
    [opts[i], opts[j]] = [opts[j], opts[i]];
    return { ...d, options: opts };
  });

  const optionsBySection = useMemo(() => {
    const out = {};
    (data?.options || []).forEach((o, index) => { (out[o.section] = out[o.section] || []).push({ o, index }); });
    return out;
  }, [data]);

  const pickImage = useCallback(() => {
    if (!frappe.ui?.FileUploader) return;
    new frappe.ui.FileUploader({
      allow_multiple: false,
      restrictions: { allowed_file_types: ["image/*"] },
      make_attachments_public: true,
      ...(isNew ? {} : { doctype: "Item", docname: itemCode, fieldname: "image" }),
      on_success: (file) => set({ image: file.file_url }),
    });
  }, [isNew, itemCode]);

  const errorOf = (e, fallback) => {
    const msg = (() => {
      try { return JSON.parse(JSON.parse(e?._server_messages || "[]")[0] || "{}").message; } catch { return null; }
    })();
    return (msg || fallback).replace(/<[^>]+>/g, "");
  };

  const buildPayload = () => ({
    ...data,
    item_code: isNew ? undefined : itemCode,
    sections: data.sections.map(({ _key, ...s }) => s),
    options: data.options.map(({ item_name, ...o }) => o), // eslint-disable-line no-unused-vars
    ...(sizes?.values?.length ? {
      sizes: { attribute: sizes.attribute, values: sizes.values.map(({ value, price, enabled }) => ({ value, price, enabled: enabled === false ? 0 : 1 })) },
    } : {}),
    ...(recipeTouched ? { recipe: (recipe?.lines || []).map(({ item_code, qty }) => ({ item_code, qty })) } : {}),
    ...(menuState ? { in_menu: menuState.in_menu ? 1 : 0, menu_rate: menuState.rate || 0 } : {}),
  });

  const showPreview = async () => {
    setPreviewing(true);
    setError(null);
    try {
      const r = await callWithApproval(`${API}.preview`, { data: JSON.stringify(buildPayload()) });
      setPicked(null);
      setPreview(r);
    } catch (e) {
      setError(errorOf(e, __("The preview could not be built")));
    } finally {
      setPreviewing(false);
    }
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const payload = buildPayload();
      const r = await callWithApproval(`${API}.save_item`, { data: JSON.stringify(payload), menu });
      frappe.show_alert({ message: __("{0} saved", [r.item.item_name]), indicator: "green" });
      onSaved?.(r.item, r.menu);
      onClose();
    } catch (e) {
      setError(errorOf(e, __("The item could not be saved")));
    } finally {
      setSaving(false);
    }
  };

  // ── sizes ──
  const sizeAttrs = lookups?.attributes || [];
  const startSizes = () => {
    const attr = sizeAttrs.find((a) => a.name === "Size") || sizeAttrs[0];
    const vals = attr?.values?.length ? attr.values.slice(0, 2) : ["Small", "Large"];
    setSizes({ attribute: attr?.name || "Size", values: vals.map((v) => ({ value: v, price: data.price || "", enabled: true })), isNew: true });
  };
  const setSize = (i, patch) => setSizes((sz) => ({ ...sz, values: sz.values.map((v, j) => (j === i ? { ...v, ...patch } : v)) }));
  const addSize = () => setSizes((sz) => ({ ...sz, values: [...sz.values, { value: "", price: "", enabled: true }] }));
  const removeSize = (i) => setSizes((sz) => {
    const values = sz.values.filter((_, j) => j !== i);
    return values.length || !sz.isNew ? { ...sz, values } : null;
  });
  const attrValues = sizeAttrs.find((a) => a.name === sizes?.attribute)?.values || [];

  // ── recipe ──
  const setLine = (i, patch) => { setRecipeTouched(true); setRecipe((r) => ({ ...r, lines: r.lines.map((l, j) => (j === i ? { ...l, ...patch } : l)) })); };
  const removeLine = (i) => { setRecipeTouched(true); setRecipe((r) => ({ ...r, lines: r.lines.filter((_, j) => j !== i) })); };
  const addLine = (row) => {
    setRecipeTouched(true);
    setRecipe((r) => ({ ...r, lines: [...(r?.lines || []), { item_code: row.item_code, item_name: row.item_name, uom: row.uom, qty: "", unit_cost: null }] }));
  };
  const recipeCost = (recipe?.lines || []).reduce((t, l) => t + (Number(l.qty) || 0) * (Number(l.unit_cost) || 0), 0);
  const money = (v) => (typeof REN !== "undefined" && REN.format_currency ? REN.format_currency(v) : `$ ${Number(v || 0).toFixed(2)}`);

  // ── preview dialog ──
  const previewItems = useMemo(() => Object.fromEntries((preview?.items || []).map((i) => [i.item_code, i])), [preview]);
  const groupsOf = useCallback((code) => (previewItems[code]?.modifier_groups || [])
    .map((n) => preview?.modifier_groups?.[n]).filter((g) => g?.options?.length), [previewItems, preview]);
  const resolveVariant = useCallback((code) => {
    const item = previewItems[code];
    return item ? { item, groups: groupsOf(code), fromComponents: !!item.price_from_components } : null;
  }, [previewItems, groupsOf]);
  const previewItem = preview?.items?.[0];

  const tabs = [
    ["basics", __("Basics")],
    ...(data?.variant_of ? [] : [["sizes", `${__("Sizes")}${sizes?.values?.length ? ` · ${sizes.values.length}` : ""}`]]),
    ["options", `${__("Options & combo")}${data?.options?.length ? ` · ${data.options.length}` : ""}`],
    ["recipe", `${__("Recipe")}${recipe?.lines?.length ? ` · ${recipe.lines.length}` : ""}`],
  ];

  return (
    <div className="ren-portal fixed inset-0 z-[1040] flex items-end sm:items-center justify-center bg-black/60 animate-fade-in" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()}
        className="w-full sm:max-w-2xl h-[94vh] sm:h-[88vh] flex flex-col bg-card text-card-foreground border border-border rounded-t-3xl sm:rounded-2xl shadow-2xl animate-slide-up">
        {/* header */}
        <div className="shrink-0 flex items-center gap-3 px-5 pt-4 pb-3 border-b border-border">
          <div className="flex-1 min-w-0">
            <div className="text-lg font-semibold truncate">{isNew ? __("New item") : (data?.item_name || itemCode)}</div>
            <div className="text-xs text-muted-foreground truncate">
              {isNew ? __("Creates an ERPNext Item") : `${__("Item")} ${itemCode}`}{menu ? ` · ${__("Menu")} ${menu}` : ""}
            </div>
          </div>
          <button onClick={onClose} className="w-9 h-9 -mr-2 rounded-xl text-muted-foreground hover:bg-muted flex items-center justify-center" aria-label={__("Close")}>
            <X size={20} />
          </button>
        </div>
        <div className="shrink-0 flex gap-1 px-5 pt-2 border-b border-border">
          {tabs.map(([k, label]) => (
            <button key={k} onClick={() => setTab(k)}
              className={`px-3 py-2 text-sm font-semibold border-b-2 -mb-px ${tab === k ? "border-blue-500 text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
              {label}
            </button>
          ))}
        </div>

        {/* body */}
        <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-5 py-4">
          {!data ? (
            <div className="py-16 flex justify-center text-muted-foreground"><Loader2 className="animate-spin" /></div>
          ) : tab === "basics" ? (
            <div className="flex flex-col gap-4">
              <div className="flex gap-4">
                <button type="button" onClick={pickImage}
                  className="shrink-0 w-28 h-28 rounded-xl border border-dashed border-border bg-muted/20 overflow-hidden flex items-center justify-center text-muted-foreground hover:bg-muted/40 relative group">
                  {data.image
                    ? <img src={data.image} alt="" className="w-full h-full object-cover" />
                    : <span className="flex flex-col items-center gap-1 text-xs"><ImagePlus size={20} />{__("Photo")}</span>}
                </button>
                <div className="flex-1 min-w-0 space-y-3">
                  <Field label={__("Name")}>
                    <input autoFocus={isNew} value={data.item_name} onChange={(e) => set({ item_name: e.target.value })} className={input} />
                  </Field>
                  <Field label={__("Group")}>
                    <select value={data.item_group || ""} onChange={(e) => set({ item_group: e.target.value })} className={input}>
                      <option value="" disabled>{__("Choose a group")}</option>
                      {(lookups?.item_groups || []).map((g) => <option key={g} value={g}>{g}</option>)}
                    </select>
                  </Field>
                </div>
              </div>
              {data.image && (
                <button type="button" onClick={() => set({ image: "" })} className="text-xs text-muted-foreground hover:text-destructive">{__("Remove photo")}</button>
              )}

              <div className="grid grid-cols-2 gap-3">
                <Field label={__("Price")} hint={data.has_variants ? __("Each size has its own price") : meta.price_list || null}>
                  <NumberInput value={data.has_variants ? "" : data.price ?? ""} onChange={(v) => set({ price: v })}
                    placeholder={data.has_variants ? __("By size") : "0.00"} className={data.has_variants ? "opacity-50 pointer-events-none" : ""} />
                </Field>
                {menuState && (
                  <Field label={__("Price on this menu")} hint={__("Empty = the price")}>
                    <NumberInput value={menuState.rate || ""} onChange={(v) => setMenuState((m) => ({ ...m, rate: v }))} placeholder={__("Same")} />
                  </Field>
                )}
              </div>

              {menuState && (
                <Toggle checked={menuState.in_menu} onChange={(v) => setMenuState((m) => ({ ...m, in_menu: v }))}
                  label={__("On menu {0}", [menu])} />
              )}

              <Field label={__("Description")}>
                <textarea value={data.description} onChange={(e) => set({ description: e.target.value })} rows={3}
                  className="w-full px-3 py-2 rounded-lg bg-background border border-border text-sm outline-none focus:border-blue-500 resize-none" />
              </Field>

              {lookups?.tags?.length > 0 && (
                <Field label={__("Dietary & allergens")}>
                  <div className="flex flex-wrap gap-1.5">
                    {lookups.tags.map((t) => {
                      const on = data.tags.includes(t.name);
                      return (
                        <button key={t.name} type="button"
                          onClick={() => set({ tags: on ? data.tags.filter((x) => x !== t.name) : [...data.tags, t.name] })}
                          style={on ? { borderColor: t.color, color: t.color } : undefined}
                          className={`px-2.5 py-1 rounded-full border text-xs font-semibold ${on ? "bg-white/5" : "border-border text-muted-foreground hover:text-foreground"}`}>
                          {__(t.name)}
                        </button>
                      );
                    })}
                  </div>
                </Field>
              )}

              {isNew && (
                <Toggle checked={!!data.is_stock_item} onChange={(v) => set({ is_stock_item: v ? 1 : 0 })}
                  label={__("Keep stock of this item")}
                  hint={__("Bottled drinks, desserts bought ready… Dishes made in the kitchen use a recipe instead.")} />
              )}
            </div>
          ) : tab === "sizes" ? (
            <div className="flex flex-col gap-4">
              {!sizes ? (
                sold && !isNew ? (
                  <p className="text-sm text-muted-foreground">
                    {__("This item has already been sold, so it can't be turned into sizes (its past sales would point to a template). Create a new item with its sizes and take this one off the menu.")}
                  </p>
                ) : (
                  <div className="rounded-xl border border-dashed border-border p-5 text-center flex flex-col items-center gap-3">
                    <p className="text-sm text-muted-foreground m-0">
                      {__("Sizes (Small, Medium, Large…) are ERPNext variants: each one is its own item with its own price, stock and recipe. The waiter picks the size; the options are shared.")}
                    </p>
                    <button type="button" onClick={startSizes}
                      className="h-10 px-4 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold inline-flex items-center gap-2">
                      <Plus size={16} /> {__("Add sizes")}
                    </button>
                  </div>
                )
              ) : (
                <>
                  <Field label={__("Sizes by")} hint={sizes.isNew ? __("An ERPNext Item Attribute; new values are added to it") : null}>
                    {sizes.isNew ? (
                      <select value={sizes.attribute} onChange={(e) => setSizes((sz) => ({ ...sz, attribute: e.target.value }))} className={input}>
                        {!sizeAttrs.some((a) => a.name === "Size") && <option value="Size">Size</option>}
                        {sizeAttrs.map((a) => <option key={a.name} value={a.name}>{a.name}</option>)}
                      </select>
                    ) : (
                      <div className={`${input} flex items-center opacity-70`}>{sizes.attribute}</div>
                    )}
                  </Field>
                  <datalist id="ren-size-values">{attrValues.map((v) => <option key={v} value={v} />)}</datalist>
                  <div className="rounded-xl border border-border divide-y divide-border">
                    <div className="grid grid-cols-[1fr_7rem_5.5rem_2.5rem] gap-2 px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                      <span>{__("Size")}</span><span>{__("Price")}</span><span>{__("On sale")}</span><span />
                    </div>
                    {sizes.values.map((v, i) => (
                      <div key={v.item_code || `n${i}`} className="grid grid-cols-[1fr_7rem_5.5rem_2.5rem] gap-2 px-3 py-2 items-center">
                        {v.item_code ? (
                          <span className="min-w-0">
                            <span className="block text-sm font-medium truncate">{v.value}</span>
                            <span className="block text-[10px] text-muted-foreground truncate">{v.item_code}</span>
                          </span>
                        ) : (
                          <input list="ren-size-values" value={v.value} onChange={(e) => setSize(i, { value: e.target.value })}
                            placeholder={__("e.g. Medium")} className={`${input} h-9`} />
                        )}
                        <NumberInput small value={v.price ?? ""} onChange={(val) => setSize(i, { price: val })} placeholder="0.00" className="w-full" />
                        <span><Toggle checked={v.enabled !== false} onChange={(on) => setSize(i, { enabled: on })} label="" /></span>
                        {v.item_code ? <span /> : (
                          <button type="button" onClick={() => removeSize(i)} className="w-8 h-8 rounded-lg text-destructive/70 hover:text-destructive hover:bg-destructive/10 flex items-center justify-center" aria-label={__("Remove")}>
                            <Trash2 size={15} />
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                  <button type="button" onClick={addSize}
                    className="w-full h-10 rounded-xl border border-dashed border-border text-sm font-semibold text-muted-foreground hover:text-foreground hover:bg-muted/40 flex items-center justify-center gap-2">
                    <Plus size={16} /> {__("Add size")}
                  </button>
                  <p className="text-xs text-muted-foreground">
                    {__("A size that was sold can't be deleted: turn it off. The card shows \"from\" the cheapest size.")}
                  </p>
                </>
              )}
            </div>
          ) : tab === "recipe" ? (
            <div className="flex flex-col gap-4">
              {data.is_stock_item ? (
                <p className="text-sm text-muted-foreground">
                  {__("This item is kept in stock (it's sold as it was bought), so it has no recipe. Recipes are for dishes made in the kitchen: their ingredients are taken out of stock when they're sold.")}
                </p>
              ) : (
                <>
                  <p className="text-xs text-muted-foreground m-0">
                    {__("What one portion uses. Saved as an ERPNext BOM; ingredients are taken out of stock when the dish is sold. Removed or extra options adjust it.")}
                    {sizes?.values?.length ? ` ${__("Sizes without a recipe of their own use this one.")}` : ""}
                  </p>
                  {recipe?.inherited && !recipeTouched && (
                    <p className="text-xs text-amber-400 m-0">{__("This uses its template's recipe; changing it here gives this size its own.")}</p>
                  )}
                  <div className="rounded-xl border border-border divide-y divide-border">
                    {(recipe?.lines || []).length === 0 && (
                      <p className="px-3 py-4 text-sm text-muted-foreground m-0">{__("No ingredients yet.")}</p>
                    )}
                    {(recipe?.lines || []).map((l, i) => (
                      <div key={`${l.item_code}-${i}`} className="grid grid-cols-[1fr_6rem_3.5rem_5rem_2.5rem] gap-2 px-3 py-2 items-center">
                        <span className="min-w-0">
                          <span className="block text-sm font-medium truncate">{l.item_name || l.item_code}</span>
                          <span className="block text-[10px] text-muted-foreground truncate">{l.item_code}</span>
                        </span>
                        <NumberInput small value={l.qty ?? ""} onChange={(v) => setLine(i, { qty: v })} placeholder="0" className="w-full" />
                        <span className="text-xs text-muted-foreground truncate">{l.uom}</span>
                        <span className="text-xs tabular-nums text-right">{l.unit_cost != null ? money((Number(l.qty) || 0) * l.unit_cost) : "—"}</span>
                        <button type="button" onClick={() => removeLine(i)} className="w-8 h-8 rounded-lg text-destructive/70 hover:text-destructive hover:bg-destructive/10 flex items-center justify-center" aria-label={__("Remove")}>
                          <Trash2 size={15} />
                        </button>
                      </div>
                    ))}
                  </div>
                  {ingPicking ? (
                    <ItemPicker method="search_ingredients" placeholder={__("Search ingredients (stock items)")}
                      onClose={() => setIngPicking(false)} onPick={(r) => { addLine(r); setIngPicking(false); }} />
                  ) : (
                    <button type="button" onClick={() => setIngPicking(true)}
                      className="w-full h-10 rounded-xl border border-dashed border-border text-sm font-semibold text-muted-foreground hover:text-foreground hover:bg-muted/40 flex items-center justify-center gap-2">
                      <Plus size={16} /> {__("Add ingredient")}
                    </button>
                  )}
                  <div className="rounded-xl bg-muted/30 px-4 py-3 flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">{__("Cost per portion")}{recipeTouched ? ` (${__("current costs")})` : ""}</span>
                    <span className="font-semibold tabular-nums">
                      {money(recipeCost)}
                      {Number(data.price) > 0 && recipeCost > 0 && (
                        <span className="ml-2 text-xs text-muted-foreground">· {__("{0}% of the price", [Math.round(recipeCost / Number(data.price) * 100)])}</span>
                      )}
                    </span>
                  </div>
                </>
              )}
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              <div className="rounded-xl border border-border p-3">
                <Toggle checked={!!data.price_from_components} onChange={(v) => set({ price_from_components: v ? 1 : 0 })}
                  label={__("Price from what is chosen")}
                  hint={__("Build-your-own: the price is the sum of the options chosen (the item's price is not used).")} />
                <Toggle checked={!!data.route_components} onChange={(v) => set({ route_components: v ? 1 : 0 })}
                  label={__("Send components to their stations")}
                  hint={__("A combo: the burger goes to the grill, the drink to the bar.")} />
              </div>

              {data.sections.length === 0 && (
                <p className="text-sm text-muted-foreground">
                  {__("No options. Add a section: Ingredients (what comes in it), Cooking point, Sides, the parts of a combo…")}
                </p>
              )}
              {data.sections.map((s) => (
                <SectionCard key={s._key} section={s} lookups={lookups} fromComponents={!!data.price_from_components}
                  options={optionsBySection[s.section] || []}
                  onChange={(patch) => updateSection(s._key, patch)} onRemove={() => removeSection(s._key)}
                  onOption={updateOption} onRemoveOption={removeOption} onMoveOption={moveOption}
                  onAddOption={(o) => addOption(s.section, o)} />
              ))}
              <button type="button" onClick={addSection}
                className="w-full h-11 rounded-xl border border-dashed border-border text-sm font-semibold text-muted-foreground hover:text-foreground hover:bg-muted/40 flex items-center justify-center gap-2">
                <Plus size={16} /> {__("Add section")}
              </button>
            </div>
          )}
        </div>

        {/* footer */}
        <div className="shrink-0 px-5 pt-3 border-t border-border space-y-2" style={{ paddingBottom: "max(0.75rem, env(safe-area-inset-bottom))" }}>
          {error && <p className="text-sm text-destructive whitespace-pre-line">{error}</p>}
          <div className="flex gap-2">
            {!isNew && (
              <a href={`/desk/item/${encodeURIComponent(itemCode)}`} target="_blank" rel="noreferrer"
                className="h-11 px-4 rounded-xl bg-muted text-sm font-semibold flex items-center text-muted-foreground hover:text-foreground">
                {__("Open in desk")}
              </a>
            )}
            <button onClick={showPreview} disabled={previewing || !data?.item_name?.trim() || !data?.item_group}
              className="h-11 px-4 rounded-xl bg-muted text-sm font-semibold flex items-center gap-2 disabled:opacity-40">
              {previewing ? <Loader2 size={16} className="animate-spin" /> : <Eye size={16} />} {__("Preview")}
            </button>
            <button onClick={onClose} className="h-11 px-4 rounded-xl bg-muted text-sm font-semibold ml-auto">{__("Cancel")}</button>
            <button onClick={save} disabled={saving || !data?.item_name?.trim() || !data?.item_group}
              className="h-11 px-6 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-bold disabled:opacity-40 flex items-center gap-2">
              {saving && <Loader2 size={16} className="animate-spin" />} {isNew ? __("Create") : __("Save")}
            </button>
          </div>
        </div>
      </div>

      {preview && previewItem && (
        <div onClick={(e) => e.stopPropagation()}>
          {picked ? (
            <div className="fixed inset-0 z-[1050] flex items-center justify-center bg-black/60" onClick={() => setPreview(null)}>
              <div className="w-full max-w-sm m-4 rounded-2xl bg-card border border-border p-5 space-y-3" onClick={(e) => e.stopPropagation()}>
                <div className="text-xs uppercase tracking-wide text-muted-foreground">{__("The order line would be")}</div>
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-lg font-semibold">{picked.qty} × {picked.name}</span>
                  <span className="text-lg font-bold tabular-nums">{money(picked.total)}</span>
                </div>
                {picked.texts.length > 0 && <div className="text-sm text-muted-foreground">{picked.texts.join(", ")}</div>}
                <div className="flex gap-2 pt-2">
                  <button onClick={() => setPicked(null)} className="flex-1 h-10 rounded-xl bg-muted text-sm font-semibold">{__("Try again")}</button>
                  <button onClick={() => setPreview(null)} className="flex-1 h-10 rounded-xl bg-blue-600 text-white text-sm font-semibold">{__("Done")}</button>
                </div>
              </div>
            </div>
          ) : (
            <ModifierDialog
              item={previewItem}
              groups={groupsOf(previewItem.item_code)}
              allGroups={preview.modifier_groups || {}}
              modes={preview.modifier_modes || []}
              fromComponents={!!previewItem.price_from_components}
              variants={previewItem.variants || null}
              resolveVariant={previewItem.variants ? resolveVariant : null}
              showQty
              onConfirm={({ modifiers, qty, item }) => {
                const it = item || previewItem;
                const unit = Math.max((it.price_from_components ? 0 : Number(it.price_list_rate) || 0) + sumModifiers(modifiers), 0);
                setPicked({ qty: qty || 1, name: it.item_name, texts: modifierTexts(modifiers), total: unit * (qty || 1) });
              }}
              onClose={() => setPreview(null)}
            />
          )}
        </div>
      )}
    </div>
  );
}

export default ItemEditor;
