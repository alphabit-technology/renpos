import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ShoppingBag, Plus, Minus, X, Search, ChevronRight, Clock, Check, ChefHat, Bell, Loader2, MapPin, Utensils,
  CalendarClock, ArrowLeft, Truck, Home,
} from "lucide-react";
import { ModifierDialog } from "@c/order/src/ModifierDialog";
import { modifierTexts, modifiersKey, sumModifiers } from "@c/order/modifierRules";
import { GuestAPI } from "./api";

/**
 * Guest ordering (the /order page, see www/order.py and api/online.py).
 *
 *   ?r=<restaurant>  pickup: menu, cart, name / phone / pickup time
 *   ?r=..&d=<ZIP>    delivery from that branch (the ZIP code picked it):
 *                    address, fee, minimum order, delivery time
 *   ?t=<table code>  at the table: menu, cart, optional name
 *   ?o=<token>       the order's progress (polls), "order more" at a table
 *
 * Prices shown are the menu's; the server prices the order again (the guest
 * never sends prices). Options use the same dialog and rules as the POS.
 */

const store = {
  get(key, fallback) {
    try { const v = localStorage.getItem(key); return v ? JSON.parse(v) : fallback; } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private mode */ }
  },
};

let currency = "USD";
const money = (v) => {
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(Number(v) || 0);
  } catch {
    return `$${(Number(v) || 0).toFixed(2)}`;
  }
};
const localDate = (s) => (s ? new Date(String(s).replace(" ", "T")) : null);
const timeText = (s) => localDate(s)?.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) || "";

function setUrl(params) {
  const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v));
  window.history.replaceState(null, "", `${window.location.pathname}?${qs}`);
}

// ─────────────────────────────────────────────
// Small pieces
// ─────────────────────────────────────────────

function Centered({ children }) {
  return <div className="min-h-[100dvh] flex flex-col items-center justify-center px-6 text-center gap-3">{children}</div>;
}

function Spinner() {
  return <Centered><Loader2 className="animate-spin text-neutral-400" size={28} /></Centered>;
}

function ErrorScreen({ message, onRetry }) {
  return (
    <Centered>
      <div className="w-14 h-14 rounded-full bg-neutral-100 flex items-center justify-center"><Utensils size={24} /></div>
      <p className="text-lg font-semibold m-0 max-w-sm">{message}</p>
      {onRetry && (
        <button onClick={onRetry} className="mt-2 h-11 px-5 rounded-full bg-neutral-900 text-white font-semibold">
          {__("Try again")}
        </button>
      )}
    </Centered>
  );
}

function Stepper({ qty, onChange, small }) {
  const size = small ? "w-8 h-8" : "w-10 h-10";
  return (
    <div className="flex items-center gap-1">
      <button onClick={() => onChange(qty - 1)} aria-label={__("Less")}
        className={`${size} rounded-full border border-neutral-300 flex items-center justify-center active:bg-neutral-100`}>
        <Minus size={16} />
      </button>
      <span className="w-7 text-center font-semibold tabular-nums">{qty}</span>
      <button onClick={() => onChange(qty + 1)} aria-label={__("More")}
        className={`${size} rounded-full border border-neutral-300 flex items-center justify-center active:bg-neutral-100`}>
        <Plus size={16} />
      </button>
    </div>
  );
}

// ─────────────────────────────────────────────
// Menu
// ─────────────────────────────────────────────

function ItemRow({ item, inCart, onAdd }) {
  const from = item.variants || item.price_from_components;
  return (
    <button onClick={() => onAdd(item)}
      className="w-full text-left flex gap-3 py-4 border-b border-neutral-100 active:bg-neutral-50">
      <div className="flex-1 min-w-0">
        <div className="font-semibold text-[15px] leading-snug">
          {item.item_name}
          {inCart > 0 && (
            <span className="ml-2 align-middle inline-flex items-center justify-center min-w-5 h-5 px-1.5 rounded-full bg-neutral-900 text-white text-[11px] font-bold">
              {inCart}
            </span>
          )}
        </div>
        {item.description && <div className="text-sm text-neutral-500 mt-0.5 line-clamp-2">{item.description}</div>}
        <div className="mt-1.5 flex items-center gap-2 flex-wrap">
          <span className="text-[15px] tabular-nums">
            {from ? __("from {0}", [money(item.price_list_rate)]) : money(item.price_list_rate)}
          </span>
          {(item.tags || []).map((t) => (
            <span key={t} className="text-[11px] px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 font-medium">{__(t)}</span>
          ))}
        </div>
      </div>
      {item.image ? (
        <div className="relative shrink-0">
          <img src={item.image} alt="" loading="lazy" className="w-24 h-24 rounded-xl object-cover bg-neutral-100" />
          <span className="absolute -bottom-1 -right-1 w-9 h-9 rounded-full bg-white shadow-md border border-neutral-200 flex items-center justify-center">
            <Plus size={18} />
          </span>
        </div>
      ) : (
        <span className="shrink-0 self-center w-9 h-9 rounded-full bg-white shadow-md border border-neutral-200 flex items-center justify-center">
          <Plus size={18} />
        </span>
      )}
    </button>
  );
}

function GroupTabs({ groups, active, onPick }) {
  const ref = useRef(null);
  useEffect(() => {
    ref.current?.querySelector(`[data-g="${CSS.escape(active || "")}"]`)?.scrollIntoView({ inline: "center", block: "nearest" });
  }, [active]);
  return (
    <div ref={ref} className="flex gap-2 overflow-x-auto no-scrollbar px-4 py-2">
      {groups.map((g) => (
        <button key={g} data-g={g} onClick={() => onPick(g)}
          className={`shrink-0 h-9 px-4 rounded-full text-sm font-semibold whitespace-nowrap transition-colors ${
            active === g ? "bg-neutral-900 text-white" : "bg-neutral-100 text-neutral-700"
          }`}>
          {__(g)}
        </button>
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────
// Cart / checkout
// ─────────────────────────────────────────────

function Checkout({ menu, cart, setQty, onClose, onPlace, placing, error }) {
  const delivery = menu.mode === "delivery" ? menu.delivery : null;
  const pickup = menu.mode === "pickup";
  const contact = pickup || !!delivery;  // name and phone required
  const saved = store.get("ren_guest_contact", {});
  const [name, setName] = useState(saved.name || "");
  const [phone, setPhone] = useState(saved.phone || "");
  const [address, setAddress] = useState(saved.address || "");
  const [when, setWhen] = useState("");
  const [notes, setNotes] = useState("");
  const subtotal = cart.reduce((s, l) => s + l.unit * l.qty, 0);
  const fee = delivery ? Number(delivery.fee) || 0 : 0;
  const missing = delivery ? Math.max((Number(delivery.minimum) || 0) - subtotal, 0) : 0;
  const valid = (!contact || (name.trim() && phone.replace(/\D/g, "").length >= 7))
    && (!delivery || (address.trim() && missing <= 0));

  const submit = () => {
    if (!valid || placing) return;
    store.set("ren_guest_contact", { name: name.trim(), phone: phone.trim(), address: address.trim() || saved.address || "" });
    onPlace({
      guest_name: name.trim(), phone: phone.trim(), pickup_at: when || undefined, notes: notes.trim() || undefined,
      address_line: delivery ? address.trim() : undefined,
    });
  };

  const input = "w-full h-12 px-4 rounded-xl border border-neutral-300 bg-white text-[16px] outline-none focus:border-neutral-900";
  return (
    <div className="fixed inset-0 z-[1000] bg-black/50 flex items-end sm:items-center justify-center" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()}
        className="w-full sm:max-w-lg max-h-[94dvh] flex flex-col bg-white rounded-t-3xl sm:rounded-3xl shadow-2xl">
        <div className="shrink-0 flex items-center gap-3 px-5 pt-4 pb-3 border-b border-neutral-100">
          <div className="flex-1">
            <div className="text-lg font-bold">{__("Your order")}</div>
            <div className="text-sm text-neutral-500">
              {delivery ? __("Delivery to {0} from {1}", [delivery.zip, menu.restaurant.title])
                : pickup ? __("Pickup at {0}", [menu.restaurant.title]) : menu.table ? __("Table {0}", [menu.table]) : menu.restaurant.title}
            </div>
          </div>
          <button onClick={onClose} aria-label={__("Close")} className="w-10 h-10 -mr-2 rounded-full flex items-center justify-center hover:bg-neutral-100">
            <X size={20} />
          </button>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-5">
          {cart.map((l) => (
            <div key={l.key} className="flex gap-3 py-3 border-b border-neutral-100">
              <div className="flex-1 min-w-0">
                <div className="font-semibold">{l.item_name}</div>
                {l.texts.length > 0 && <div className="text-sm text-neutral-500">{l.texts.join(", ")}</div>}
                <div className="text-sm tabular-nums mt-1">{money(l.unit * l.qty)}</div>
              </div>
              <Stepper small qty={l.qty} onChange={(q) => setQty(l.key, q)} />
            </div>
          ))}

          <div className="py-4 space-y-3">
            {delivery && (
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wide text-neutral-500 mb-1.5">{__("Delivery address")}</label>
                <div className="relative">
                  <Home size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-neutral-400 pointer-events-none" />
                  <input value={address} onChange={(e) => setAddress(e.target.value)} autoComplete="street-address"
                    placeholder={__("Street, number, apartment")} className={`${input} pl-11`} />
                </div>
                <p className="text-xs text-neutral-500 mt-1.5 mb-0">{__("ZIP code {0}", [delivery.zip])}</p>
              </div>
            )}
            {contact && (
              <>
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wide text-neutral-500 mb-1.5">
                    {delivery ? __("Delivery time") : __("Pickup time")}
                  </label>
                  <div className="relative">
                    <Clock size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-neutral-400 pointer-events-none" />
                    <select value={when} onChange={(e) => setWhen(e.target.value)} className={`${input} pl-11 appearance-none`}>
                      <option value="">{__("As soon as possible (about {0} min)", [menu.prep_minutes])}</option>
                      {(menu.slots || []).map((s) => <option key={s} value={s}>{timeText(s)}</option>)}
                    </select>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wide text-neutral-500 mb-1.5">{__("Name")}</label>
                    <input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" className={input} />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wide text-neutral-500 mb-1.5">{__("Phone")}</label>
                    <input value={phone} onChange={(e) => setPhone(e.target.value)} type="tel" autoComplete="tel" className={input} />
                  </div>
                </div>
              </>
            )}
            {!contact && (
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wide text-neutral-500 mb-1.5">{__("Your name (optional)")}</label>
                <input value={name} onChange={(e) => setName(e.target.value)} autoComplete="given-name" className={input} />
              </div>
            )}
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wide text-neutral-500 mb-1.5">{__("Notes for the kitchen")}</label>
              <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} maxLength={300}
                placeholder={__("Allergies, special requests...")}
                className="w-full px-4 py-3 rounded-xl border border-neutral-300 text-[16px] outline-none focus:border-neutral-900 resize-none" />
            </div>
            <div className="flex justify-between text-[15px]">
              <span className="text-neutral-500">{__("Subtotal")}</span>
              <span className="font-semibold tabular-nums">{money(subtotal)}</span>
            </div>
            {delivery && (
              <div className="flex justify-between text-[15px]">
                <span className="text-neutral-500">{__("Delivery fee")}</span>
                <span className="font-semibold tabular-nums">{fee ? money(fee) : __("Free")}</span>
              </div>
            )}
            {missing > 0 && (
              <div className="text-sm text-amber-800 bg-amber-50 rounded-xl px-4 py-3">
                {__("The minimum for delivery is {0}. Add {1} more.", [money(delivery.minimum), money(missing)])}
              </div>
            )}
            <p className="text-xs text-neutral-500 m-0">
              {menu.tax_inclusive ? __("Prices include tax.") : __("Tax is added to the total.")}{" "}
              {delivery ? __("You pay when it arrives.") : pickup ? __("You pay when you pick it up.") : __("You pay with your server.")}
            </p>
            {error && <div className="text-sm text-red-600 bg-red-50 rounded-xl px-4 py-3 whitespace-pre-line">{error}</div>}
          </div>
        </div>

        <div className="shrink-0 px-5 pt-3 border-t border-neutral-100" style={{ paddingBottom: "max(0.75rem, env(safe-area-inset-bottom))" }}>
          <button onClick={submit} disabled={!valid || placing || !cart.length}
            className="w-full h-14 rounded-2xl bg-neutral-900 text-white font-bold text-[16px] flex items-center justify-center gap-2 disabled:opacity-40">
            {placing && <Loader2 size={18} className="animate-spin" />}
            {delivery ? __("Place delivery order") : pickup ? __("Place pickup order") : __("Send order")}
            <span className="tabular-nums">· {money(subtotal + fee)}</span>
          </button>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// Menu screen
// ─────────────────────────────────────────────

function MenuScreen({ where, onPlaced, onChangeZip }) {
  const [menu, setMenu] = useState(null);
  const [error, setError] = useState(null);
  const [reload, setReload] = useState(0);
  const cartKey = `ren_guest_cart:${where.t || where.r}`;
  const [cart, setCart] = useState(() => store.get(cartKey, []));
  const [dialog, setDialog] = useState(null);
  const [checkout, setCheckout] = useState(false);
  const [placing, setPlacing] = useState(false);
  const [placeError, setPlaceError] = useState(null);
  const [query, setQuery] = useState("");
  const [activeGroup, setActiveGroup] = useState(null);
  const [flash, setFlash] = useState(null);
  const sections = useRef({});
  const last = store.get(`ren_guest_last:${where.t || where.r}`, null);

  useEffect(() => {
    let alive = true;
    GuestAPI.menu(where).then((m) => {
      if (!alive) return;
      currency = m.currency || "USD";
      // drop cart lines whose item left the menu (sold out, menu changed)
      const codes = new Set(m.items.map((i) => i.item_code));
      setCart((c) => c.filter((l) => codes.has(l.item_code)));
      window.REN = { ...(window.REN || {}), format_currency: money };
      document.title = m.restaurant.title;
      setMenu(m);
      setActiveGroup(m.item_groups[0] || null);
    }).catch((e) => alive && setError(e.message));
    return () => { alive = false; };
  }, [where, reload]);

  useEffect(() => { store.set(cartKey, cart); }, [cart, cartKey]);

  const byCode = useMemo(() => Object.fromEntries((menu?.items || []).map((i) => [i.item_code, i])), [menu]);

  const groupsOf = useCallback((code) => (byCode[code]?.modifier_groups || [])
    .map((n) => menu?.modifier_groups?.[n]).filter((g) => g?.options?.length), [byCode, menu]);
  const resolveVariant = useCallback((code) => {
    const item = byCode[code];
    return item ? { item, groups: groupsOf(code), fromComponents: !!item.price_from_components } : null;
  }, [byCode, groupsOf]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (menu?.items || []).filter((i) => !i.variant_of
      && (!q || i.item_name.toLowerCase().includes(q) || (i.description || "").toLowerCase().includes(q)));
  }, [menu, query]);
  const grouped = useMemo(() => {
    const out = [];
    for (const g of menu?.item_groups || []) {
      const items = visible.filter((i) => i.item_group === g);
      if (items.length) out.push([g, items]);
    }
    return out;
  }, [menu, visible]);

  // the tab follows the section on screen
  useEffect(() => {
    if (!grouped.length) return;
    const obs = new IntersectionObserver((entries) => {
      const top = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
      if (top) setActiveGroup(top.target.dataset.group);
    }, { rootMargin: "-120px 0px -60% 0px" });
    Object.values(sections.current).forEach((el) => el && obs.observe(el));
    return () => obs.disconnect();
  }, [grouped]);

  const countOf = (code) => cart.filter((l) => l.item_code === code || byCode[l.item_code]?.variant_of === code)
    .reduce((s, l) => s + l.qty, 0);

  const addLine = (item, modifiers, qty) => {
    const unit = Math.max((item.price_from_components ? 0 : Number(item.price_list_rate) || 0) + sumModifiers(modifiers), 0);
    const key = `${item.item_code}|${modifiersKey(modifiers)}`;
    setCart((c) => {
      const found = c.find((l) => l.key === key);
      if (found) return c.map((l) => (l.key === key ? { ...l, qty: l.qty + qty } : l));
      return [...c, {
        key, item_code: item.item_code, item_name: item.item_name, unit, qty,
        texts: modifierTexts(modifiers),
        modifiers: modifiers.filter((m) => !m.removed).map((m) => ({ option: m.option, parent: m.parent, qty: m.qty, mode: m.mode })),
      }];
    });
    setFlash(__("{0} added", [item.item_name]));
    setTimeout(() => setFlash(null), 1600);
  };

  const onAdd = (item) => {
    if (item.variants || groupsOf(item.item_code).length) setDialog(item);
    else addLine(item, [], 1);
  };

  const setQty = (key, qty) => setCart((c) => (qty <= 0 ? c.filter((l) => l.key !== key) : c.map((l) => (l.key === key ? { ...l, qty } : l))));

  const place = async (body) => {
    setPlacing(true);
    setPlaceError(null);
    try {
      const res = await GuestAPI.place(where, {
        ...body,
        items: cart.map((l) => ({ item_code: l.item_code, qty: l.qty, modifiers: l.modifiers })),
      });
      setCart([]);
      store.set(`ren_guest_last:${where.t || where.r}`, res.token);
      onPlaced(res.token, res);
    } catch (e) {
      setPlaceError(e.message);
      setReload((n) => n + 1); // prices or availability may have changed
    } finally {
      setPlacing(false);
    }
  };

  if (error) return <ErrorScreen message={error} onRetry={() => { setError(null); setReload((n) => n + 1); }} />;
  if (!menu) return <Spinner />;

  const count = cart.reduce((s, l) => s + l.qty, 0);
  const subtotal = cart.reduce((s, l) => s + l.unit * l.qty, 0);
  const pickup = menu.mode === "pickup";
  const delivery = menu.mode === "delivery" ? menu.delivery : null;

  return (
    <div className="max-w-xl mx-auto min-h-[100dvh] pb-28">
      {/* header */}
      <header className="px-4 pt-5 pb-3">
        <div className="flex items-center gap-3">
          {menu.restaurant.logo && <img src={menu.restaurant.logo} alt="" className="w-12 h-12 rounded-xl object-cover" />}
          <div className="min-w-0">
            <h1 className="text-2xl font-extrabold m-0 leading-tight truncate">{menu.restaurant.title}</h1>
            <div className="flex items-center gap-1.5 text-sm text-neutral-500 mt-0.5">
              {delivery ? <Truck size={15} /> : pickup ? <ShoppingBag size={15} /> : <MapPin size={15} />}
              {delivery ? __("Delivery to {0} · about {1} min", [delivery.zip, menu.prep_minutes])
                : pickup ? __("Pickup · ready in about {0} min", [menu.prep_minutes]) : __("Ordering for table {0}", [menu.table])}
              {delivery && onChangeZip && (
                <button onClick={onChangeZip} className="ml-1 underline text-neutral-700">{__("Change")}</button>
              )}
            </div>
            {delivery && (
              <div className="text-xs text-neutral-500 mt-0.5">
                {[Number(delivery.fee) ? __("{0} delivery fee", [money(delivery.fee)]) : __("Free delivery"),
                  Number(delivery.minimum) ? __("{0} minimum", [money(delivery.minimum)]) : null].filter(Boolean).join(" · ")}
              </div>
            )}
          </div>
        </div>
        {menu.restaurant.note && <p className="mt-3 mb-0 text-sm text-neutral-600 bg-neutral-50 rounded-xl px-3 py-2 whitespace-pre-line">{menu.restaurant.note}</p>}
        {last && (
          <button onClick={() => onPlaced(last)} className="mt-3 w-full flex items-center gap-2 px-4 h-12 rounded-xl bg-emerald-50 text-emerald-800 font-semibold text-sm">
            <Bell size={16} /> <span className="flex-1 text-left">{__("See your order's progress")}</span> <ChevronRight size={16} />
          </button>
        )}
      </header>

      {/* search + groups */}
      <div className="sticky top-0 z-10 bg-white/95 backdrop-blur border-b border-neutral-100">
        <div className="px-4 pt-2">
          <div className="relative">
            <Search size={18} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-neutral-400" />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={__("Search the menu")}
              className="w-full h-11 pl-10 pr-4 rounded-full bg-neutral-100 text-[16px] outline-none" />
          </div>
        </div>
        {!query && grouped.length > 1 && (
          <GroupTabs groups={grouped.map(([g]) => g)} active={activeGroup}
            onPick={(g) => sections.current[g]?.scrollIntoView({ behavior: "smooth", block: "start" })} />
        )}
      </div>

      {/* items */}
      <main className="px-4">
        {grouped.length === 0 && <p className="text-center text-neutral-500 py-16">{__("Nothing found")}</p>}
        {grouped.map(([g, items]) => (
          <section key={g} data-group={g} ref={(el) => { sections.current[g] = el; }} className="scroll-mt-28 pt-5">
            <h2 className="text-lg font-bold m-0 mb-1">{__(g)}</h2>
            {items.map((i) => <ItemRow key={i.item_code} item={i} inCart={countOf(i.item_code)} onAdd={onAdd} />)}
          </section>
        ))}
      </main>

      {/* cart bar */}
      {count > 0 && !checkout && (
        <div className="fixed inset-x-0 bottom-0 z-20 px-4 pt-2 bg-gradient-to-t from-white via-white to-white/0"
          style={{ paddingBottom: "max(1rem, env(safe-area-inset-bottom))" }}>
          <button onClick={() => { setPlaceError(null); setCheckout(true); }}
            className="max-w-xl mx-auto w-full h-14 rounded-2xl bg-neutral-900 text-white font-bold flex items-center px-5 gap-3 shadow-lg">
            <span className="w-7 h-7 rounded-full bg-white/20 flex items-center justify-center text-sm tabular-nums">{count}</span>
            <span className="flex-1 text-left">{__("View order")}</span>
            <span className="tabular-nums">{money(subtotal)}</span>
          </button>
        </div>
      )}

      {flash && !checkout && (
        <div className="fixed left-1/2 -translate-x-1/2 bottom-24 z-30 max-w-[90vw] px-4 py-2 rounded-full bg-neutral-900 text-white text-sm shadow-lg flex items-center gap-2 whitespace-nowrap">
          <Check size={16} /> {flash}
        </div>
      )}

      {dialog && (
        <ModifierDialog
          item={dialog}
          groups={groupsOf(dialog.item_code)}
          allGroups={menu.modifier_groups || {}}
          modes={menu.modifier_modes || []}
          fromComponents={!!dialog.price_from_components}
          variants={dialog.variants || null}
          resolveVariant={dialog.variants ? resolveVariant : null}
          showQty
          onConfirm={({ modifiers, qty, item }) => { addLine(item || dialog, modifiers, qty || 1); setDialog(null); }}
          onClose={() => setDialog(null)}
        />
      )}

      {checkout && (
        <Checkout menu={menu} cart={cart} setQty={setQty} placing={placing} error={placeError}
          onClose={() => setCheckout(false)} onPlace={place} />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────
// Order progress
// ─────────────────────────────────────────────

const STATE = {
  received: { icon: Check, title: () => __("We got your order") },
  scheduled: { icon: CalendarClock, title: () => __("Scheduled") },
  preparing: { icon: ChefHat, title: () => __("Preparing your order") },
  ready: { icon: Bell, title: (pickup, delivery) => (delivery ? __("Ready, leaving soon") : pickup ? __("Ready for pickup!") : __("Your order is ready")) },
  on_the_way: { icon: Truck, title: () => __("On its way!") },
  delivered: { icon: Check, title: () => __("Delivered") },
  done: { icon: Check, title: () => __("Thank you!") },
};

function StatusScreen({ token, initial, canOrderMore, onOrderMore }) {
  const [st, setSt] = useState(initial || null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    let timer;
    const load = () => GuestAPI.status(token).then((s) => {
      if (!alive) return;
      setSt(s);
      setError(null);
      if (s.state !== "done") timer = setTimeout(load, 10000);
    }).catch((e) => {
      if (!alive) return;
      setError(e.message);
      timer = setTimeout(load, 20000);
    });
    load();
    return () => { alive = false; clearTimeout(timer); };
  }, [token]);

  if (!st) return error ? <ErrorScreen message={error} /> : <Spinner />;

  const delivery = st.mode === "delivery";
  const pickup = st.mode === "pickup";
  const steps = delivery ? ["received", "preparing", "ready", "on_the_way"] : ["received", "preparing", "ready"];
  const finished = st.state === "done" || st.state === "delivered";
  const at = st.state === "scheduled" ? 0 : finished ? steps.length : Math.max(steps.indexOf(st.state), 0);
  const S = STATE[st.state] || STATE.received;
  const Icon = S.icon;
  const subtotal = st.total - (st.tax || 0);

  return (
    <div className="max-w-xl mx-auto min-h-[100dvh] px-5 pt-8 pb-16">
      <div className="text-sm text-neutral-500">{st.restaurant}</div>
      <div className="mt-6 flex flex-col items-center text-center">
        <div className={`w-20 h-20 rounded-full flex items-center justify-center ${
          st.state === "ready" || st.state === "on_the_way" ? "bg-emerald-500 text-white animate-pulse" : "bg-neutral-900 text-white"}`}>
          <Icon size={36} />
        </div>
        <h1 className="text-2xl font-extrabold mt-4 mb-1">{S.title(pickup, delivery)}</h1>
        {delivery ? (
        <p className="text-neutral-500 m-0">
          {finished ? __("Enjoy your meal")
            : st.state === "on_the_way" ? (st.driver ? __("{0} is bringing it to {1}", [st.driver, st.address]) : __("Heading to {0}", [st.address]))
            : __("Delivery to {0} around {1}", [st.address, timeText(st.deliver_by)])}
        </p>
        ) : (
        <p className="text-neutral-500 m-0">
          {st.state === "scheduled" && __("For pickup at {0}. We'll start cooking it in time.", [timeText(st.pickup_time)])}
          {st.state === "received" && (pickup ? __("Pickup around {0}", [timeText(st.pickup_time)]) : __("Your server will confirm it shortly"))}
          {st.state === "preparing" && (pickup ? __("Pickup around {0}", [timeText(st.pickup_time)]) : __("It's in the kitchen"))}
          {st.state === "ready" && (pickup ? __("Ask for the order of {0}", [st.guest_name || `#${st.order}`]) : __("It's on its way to table {0}", [st.table]))}
          {st.state === "done" && __("Enjoy your meal")}
        </p>
        )}
        <div className="mt-2 text-xs text-neutral-400">{__("Order #{0}", [st.order])}</div>
      </div>

      {!finished && (
        <div className="mt-7 flex items-center gap-2">
          {steps.map((s, i) => (
            <div key={s} className={`h-1.5 flex-1 rounded-full ${i <= at ? "bg-neutral-900" : "bg-neutral-200"}`} />
          ))}
        </div>
      )}

      <div className="mt-8 rounded-2xl border border-neutral-200 divide-y divide-neutral-100">
        {st.lines.map((l, i) => (
          <div key={i} className="flex gap-3 px-4 py-3">
            <span className="tabular-nums font-semibold w-6">{l.qty}×</span>
            <div className="flex-1 min-w-0">
              <div className="font-medium">{l.item_name}</div>
              {l.texts?.length > 0 && <div className="text-sm text-neutral-500">{l.texts.join(", ")}</div>}
            </div>
            <span className="tabular-nums text-sm">{money(l.amount)}</span>
          </div>
        ))}
        <div className="px-4 py-3 space-y-1 text-sm">
          {(st.tax > 0 || st.delivery_fee > 0) && (
            <>
              <div className="flex justify-between text-neutral-500"><span>{__("Subtotal")}</span><span className="tabular-nums">{money(subtotal - (st.delivery_fee || 0))}</span></div>
              {st.tax > 0 && <div className="flex justify-between text-neutral-500"><span>{__("Tax")}</span><span className="tabular-nums">{money(st.tax)}</span></div>}
              {st.delivery_fee > 0 && <div className="flex justify-between text-neutral-500"><span>{__("Delivery fee")}</span><span className="tabular-nums">{money(st.delivery_fee)}</span></div>}
            </>
          )}
          <div className="flex justify-between text-[16px] font-bold"><span>{__("Total")}</span><span className="tabular-nums">{money(st.total)}</span></div>
        </div>
      </div>
      <p className="text-xs text-neutral-500 text-center mt-3">
        {delivery ? __("You pay when it arrives.") : pickup ? __("You pay when you pick it up.") : __("You pay with your server.")}
      </p>

      {canOrderMore && st.state !== "done" && (
        <button onClick={onOrderMore}
          className="mt-6 w-full h-14 rounded-2xl border-2 border-neutral-900 font-bold flex items-center justify-center gap-2">
          <ArrowLeft size={18} /> {__("Order something else")}
        </button>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────
// App
// ─────────────────────────────────────────────

function ZipForm({ onFound }) {
  const [zip, setZip] = useState(store.get("ren_guest_zip", ""));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const submit = async (e) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const q = await GuestAPI.deliveryCheck(zip);
      store.set("ren_guest_zip", q.zip);
      onFound(q);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={submit} className="mt-3">
      <div className="flex gap-2">
        <input value={zip} onChange={(e) => setZip(e.target.value)} inputMode="numeric" autoComplete="postal-code"
          maxLength={10} placeholder={__("Your ZIP code")}
          className="flex-1 h-12 px-4 rounded-xl border border-neutral-300 text-[16px] outline-none focus:border-neutral-900" />
        <button type="submit" disabled={busy || zip.replace(/\D/g, "").length < 5}
          className="h-12 px-5 rounded-xl bg-neutral-900 text-white font-semibold disabled:opacity-40 flex items-center gap-2">
          {busy && <Loader2 size={16} className="animate-spin" />}{__("Continue")}
        </button>
      </div>
      {error && <p className="text-sm text-red-600 mt-2 mb-0">{error}</p>}
    </form>
  );
}

function RestaurantPicker({ restaurants, delivery, onPick, onDelivery }) {
  if (!restaurants.length && !delivery) return <ErrorScreen message={__("Online ordering isn't available right now")} />;
  return (
    <div className="max-w-xl mx-auto px-5 pt-10 pb-10">
      {delivery && (
        <section className="mb-8">
          <h1 className="text-2xl font-extrabold flex items-center gap-2 m-0"><Truck size={24} /> {__("Delivery")}</h1>
          <p className="text-neutral-500 mt-1 mb-0">{__("Enter your ZIP code to see if we deliver to you.")}</p>
          <ZipForm onFound={onDelivery} />
        </section>
      )}
      {restaurants.length > 0 && (
        <section>
          <h1 className="text-2xl font-extrabold flex items-center gap-2 m-0"><ShoppingBag size={24} /> {__("Order for pickup")}</h1>
          <div className="mt-4 space-y-2">
            {restaurants.map((r) => (
              <button key={r.name} onClick={() => onPick(r.name)}
                className="w-full h-14 px-4 rounded-2xl border border-neutral-200 flex items-center font-semibold active:bg-neutral-50">
                <span className="flex-1 text-left">{r.title}</span><ChevronRight size={18} />
              </button>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

export default function GuestApp({ boot }) {
  const params = useMemo(() => new URLSearchParams(window.location.search), []);
  const restaurants = boot?.restaurants || [];
  const [where, setWhere] = useState(() => {
    const t = params.get("t");
    const d = params.get("d");
    const r = params.get("r") || (!t && !boot?.delivery && restaurants.length === 1 ? restaurants[0].name : null);
    return t ? { t } : r && d ? { r, d } : r ? { r } : null;
  });
  const [token, setToken] = useState(params.get("o"));
  const [placed, setPlaced] = useState(null);

  const onPlaced = (tok, res) => {
    setPlaced(res || null);
    setToken(tok);
    setUrl({ ...(where || {}), o: tok });
    window.scrollTo(0, 0);
  };

  if (token) {
    return (
      <StatusScreen token={token} initial={placed} canOrderMore={!!where?.t}
        onOrderMore={() => { setToken(null); setPlaced(null); setUrl(where); }} />
    );
  }
  if (!where) {
    return (
      <RestaurantPicker restaurants={restaurants} delivery={!!boot?.delivery}
        onPick={(r) => { setWhere({ r }); setUrl({ r }); }}
        onDelivery={(q) => { const w = { r: q.restaurant, d: q.zip }; setWhere(w); setUrl(w); }} />
    );
  }
  return (
    <MenuScreen where={where} onPlaced={onPlaced}
      onChangeZip={where.d ? () => { setWhere(null); setUrl({}); } : null} />
  );
}
