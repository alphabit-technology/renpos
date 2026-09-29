import { useState, useEffect, useCallback, useRef } from "react";
import { Loader2, RotateCw, Clock, ChefHat, StickyNote } from "lucide-react";
import Modal from "@c/ui/Modal";
import { CLIENT_ID } from "@c/order/api";

/**
 * KitchenView — kitchen display (KDS) for one production station.
 *
 * Shows the station's queue (api.kitchen.get_station_queue) as tickets,
 * oldest first. Tapping an item (or a whole ticket, for stations that
 * group by order) moves it to the next status of the station's flow.
 * Refreshes on realtime events (new orders sent, status changes) and
 * every 30 s as a fallback.
 */

const API = "restaurant_management.api.kitchen";
const REFRESH_MS = 30000;

function call(method, args = {}) {
  return new Promise((resolve, reject) => {
    frappe.call({
      method: `${API}.${method}`,
      args: { ...args, client_id: CLIENT_ID },
      callback: (r) => resolve(r.message),
      error: reject,
    });
  });
}

function minutesSince(value, now) {
  if (!value) return 0;
  const t = frappe.datetime?.str_to_obj ? frappe.datetime.str_to_obj(value) : new Date(value);
  return Math.max(0, Math.floor((now - t.getTime()) / 60000));
}

function ageClass(min) {
  if (min >= 20) return "text-rose-300 bg-rose-500/15 border-rose-500/40";
  if (min >= 10) return "text-amber-300 bg-amber-500/15 border-amber-500/40";
  return "text-emerald-300 bg-emerald-500/10 border-emerald-500/30";
}

function StatusBadge({ status, message, color }) {
  return (
    <span
      className="text-[11px] font-semibold px-2 py-0.5 rounded-full border"
      style={color ? { color, borderColor: color } : undefined}
    >
      {message || status}
    </span>
  );
}

export function KitchenView({ open, onClose, station }) {
  const [queue, setQueue] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState({}); // identifier -> true
  const [now, setNow] = useState(() => Date.now());
  const timer = useRef(null);

  const stationName = station?.name;

  const refresh = useCallback(() => {
    return call("get_station_queue", { station: stationName }).then(
      (q) => { setQueue(q); setError(null); },
      () => setError(__("Could not load the kitchen queue"))
    );
  }, [stationName]);

  // initial load, polling, clock
  useEffect(() => {
    if (!open || !stationName) return;
    let cancelled = false;
    call("get_station_queue", { station: stationName }).then(
      (q) => { if (!cancelled) setQueue(q); },
      () => { if (!cancelled) setError(__("Could not load the kitchen queue")); }
    );
    const poll = setInterval(refresh, REFRESH_MS);
    const clock = setInterval(() => setNow(Date.now()), 30000);
    return () => { cancelled = true; clearInterval(poll); clearInterval(clock); };
  }, [open, stationName, refresh]);

  // realtime: orders sent to the kitchen, status changes, order edits
  useEffect(() => {
    if (!open) return;
    const handler = () => {
      clearTimeout(timer.current);
      timer.current = setTimeout(refresh, 400);
    };
    frappe.realtime.doctype_subscribe?.("Table Order");
    const events = ["kitchen_order", "kitchen_update", "order_update"];
    events.forEach((e) => frappe.realtime.on(e, handler));
    return () => {
      clearTimeout(timer.current);
      events.forEach((e) => frappe.realtime.off(e, handler));
    };
  }, [open, refresh]);

  const advance = async (identifier) => {
    if (busy[identifier]) return;
    setBusy((b) => ({ ...b, [identifier]: true }));
    try {
      await call("advance", { station: stationName, identifier });
      await refresh();
    } catch {
      // Frappe shows the server message
    } finally {
      setBusy((b) => { const n = { ...b }; delete n[identifier]; return n; });
    }
  };

  if (!open) return null;

  const grouped = !!queue?.station?.group_items_by_order;
  const tickets = queue?.tickets || [];

  const title = (
    <div className="flex items-center gap-2 min-w-0">
      <ChefHat size={20} className="shrink-0" />
      <span className="truncate">{station.description || station.name}</span>
      <span className="text-sm font-normal text-muted-foreground">
        · {tickets.length} {__("orders")}
      </span>
    </div>
  );

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="full"
      title={title}
      headerActions={(
        <button onClick={refresh} className="p-1.5 rounded-lg hover:bg-white/10" title={__("Refresh")}>
          <RotateCw size={18} />
        </button>
      )}
    >
      {!queue && !error && (
        <div className="flex justify-center py-24 text-muted-foreground"><Loader2 className="animate-spin" /></div>
      )}
      {error && <p className="p-6 text-rose-400">{error}</p>}
      {queue && tickets.length === 0 && (
        <div className="flex flex-col items-center justify-center gap-3 py-24 text-muted-foreground">
          <ChefHat size={40} />
          <p>{__("Nothing pending. New orders appear here when they're sent.")}</p>
        </div>
      )}

      <div className="grid gap-3 p-3 [grid-template-columns:repeat(auto-fill,minmax(270px,1fr))] items-start">
        {tickets.map((t) => {
          const age = minutesSince(t.ordered_time, now);
          return (
            <article key={t.order} className="rounded-2xl border border-border bg-card flex flex-col overflow-hidden">
              <header className="flex items-start justify-between gap-2 px-3 py-2.5 border-b border-border">
                <div className="min-w-0">
                  <p className="text-lg font-extrabold leading-tight truncate">{t.table_description}</p>
                  <p className="text-xs text-muted-foreground truncate">
                    {t.room_description} · #{t.short_name}{t.dinners ? ` · ${t.dinners} ${__("guests")}` : ""}
                  </p>
                </div>
                <span className={`flex items-center gap-1 text-xs font-bold px-2 py-1 rounded-lg border tabular-nums ${ageClass(age)}`}>
                  <Clock size={12} /> {age}′
                </span>
              </header>

              {t.notes && (
                <p className="flex gap-1.5 px-3 py-2 text-xs text-amber-200 bg-amber-500/10 border-b border-border">
                  <StickyNote size={13} className="shrink-0 mt-0.5" /> {t.notes}
                </p>
              )}

              <ul className="divide-y divide-border">
                {t.items.map((i) => (
                  <li key={i.identifier}>
                    <button
                      onClick={() => !grouped && advance(i.identifier)}
                      disabled={grouped || !i.next_status}
                      className={`w-full text-left px-3 py-2.5 flex items-start gap-3 ${grouped ? "cursor-default" : "hover:bg-muted/50 active:bg-muted"}`}
                    >
                      <span className="text-xl font-extrabold tabular-nums w-8 shrink-0">{i.qty}</span>
                      <span className="flex-1 min-w-0">
                        <span className="block font-semibold leading-snug">{i.item_name}</span>
                        {i.notes && <span className="block text-xs italic text-amber-200/90">{i.notes}</span>}
                      </span>
                      <span className="shrink-0 flex flex-col items-end gap-1">
                        {busy[i.identifier]
                          ? <Loader2 size={16} className="animate-spin" />
                          : <StatusBadge status={i.status} message={i.message} color={i.color} />}
                        {!grouped && i.next_status && (
                          <span className="text-[10px] text-muted-foreground">→ {i.next_status}</span>
                        )}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>

              {grouped && t.next_status && (
                <button
                  onClick={() => advance(t.order)}
                  disabled={!!busy[t.order]}
                  className="m-2 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold flex items-center justify-center gap-2"
                >
                  {busy[t.order] && <Loader2 size={16} className="animate-spin" />}
                  {t.action || t.next_status}
                </button>
              )}
            </article>
          );
        })}
      </div>
    </Modal>
  );
}
