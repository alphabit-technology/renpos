import { useState, useEffect, useCallback } from "react";
import { Ban, Search, Loader2, RotateCcw } from "lucide-react";
import Modal from "@c/ui/Modal";
import { callWithApproval } from "@/utils/approval";

/**
 * SoldOutDialog — "86" items for the restaurant: what ran out, and bring
 * items back. Every catalog greys them out in real time and the server
 * refuses new lines of a sold-out item.
 */

const MENUS = "renpos.api.menus";
const CATALOG = "renpos.ren_pos.doctype.ren_menu.ren_menu";

export function SoldOutDialog({ open, onClose, menuName }) {
  const [soldOut, setSoldOut] = useState(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [busy, setBusy] = useState(null);

  const load = useCallback(() => frappe.call({ method: `${MENUS}.get_sold_out` }).then(
    (r) => setSoldOut(r.message || []), () => setSoldOut([])), []);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  useEffect(() => {
    if (!open || query.trim().length < 2) return undefined;
    const t = setTimeout(() => {
      frappe.call({
        method: `${CATALOG}.get_items_for_tree`,
        args: { search: query.trim(), limit_page_length: 12, ...(menuName ? { menu_name: menuName } : {}) },
      }).then((r) => setResults(r.message || []), () => setResults([]));
    }, 250);
    return () => clearTimeout(t);
  }, [open, query, menuName]);

  const toggle = async (item_code, sold_out) => {
    setBusy(item_code);
    try {
      await callWithApproval(`${MENUS}.set_sold_out`, { item_code, sold_out });
      await load();
      setResults((prev) => prev.map((i) => (i.item_code === item_code ? { ...i, is_available: !sold_out } : i)));
    } catch {
      // Frappe shows the message
    }
    setBusy(null);
  };

  if (!open) return null;
  const out = new Set((soldOut || []).map((s) => s.item_code));
  const shown = query.trim().length >= 2 ? results : [];

  return (
    <Modal open size="md" onClose={onClose} title={__("Sold Out (86)")}>
      <div className="p-4 space-y-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">{__("Sold out now")}</p>
          {soldOut === null ? <Loader2 className="animate-spin" size={18} /> : soldOut.length === 0 ? (
            <p className="text-sm text-muted-foreground">{__("Everything is available.")}</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {soldOut.map((s) => (
                <button key={s.item_code} onClick={() => toggle(s.item_code, 0)} disabled={busy === s.item_code}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-500/15 text-rose-300 text-sm hover:bg-rose-500/25"
                  title={__("Available again")}>
                  {busy === s.item_code ? <Loader2 size={13} className="animate-spin" /> : <RotateCcw size={13} />}
                  {s.item_name || s.item_code}
                </button>
              ))}
            </div>
          )}
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">{__("Mark an item as sold out")}</p>
          <div className="relative">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input autoFocus value={query} onChange={(e) => setQuery(e.target.value)} placeholder={__("Search items")}
              className="w-full h-10 pl-9 pr-3 rounded-lg border border-border bg-transparent text-sm focus:outline-none" />
          </div>
          <div className="mt-2 divide-y divide-border">
            {shown.map((i) => {
              const isOut = out.has(i.item_code);
              return (
                <div key={i.item_code} className="flex items-center gap-3 py-2">
                  <span className={`flex-1 text-sm ${isOut ? "line-through text-muted-foreground" : ""}`}>{i.item_name}</span>
                  <button onClick={() => toggle(i.item_code, isOut ? 0 : 1)} disabled={busy === i.item_code}
                    className={`flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold ${isOut
                      ? "border border-border hover:bg-muted" : "bg-rose-600 text-white hover:bg-rose-500"}`}>
                    {busy === i.item_code ? <Loader2 size={13} className="animate-spin" /> : isOut ? <RotateCcw size={13} /> : <Ban size={13} />}
                    {isOut ? __("Available") : __("86 it")}
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </Modal>
  );
}

export default SoldOutDialog;
