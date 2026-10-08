import { useState, useEffect, useCallback, useRef } from "react";
import { Loader2, RotateCw, Clock, ChefHat, StickyNote, History, Undo2, Ban, Bell, BellOff, Truck, Hourglass } from "lucide-react";
import Modal from "@c/ui/Modal";
import { CLIENT_ID } from "@c/order/api";

/**
 * KitchenView — kitchen display (KDS) for one production station.
 *
 * Shows the station's queue (api.kitchen.get_station_queue) as tickets,
 * oldest first — one ticket per round (items of an order sent together).
 * Tapping an item moves it to the next status of the station's flow; for
 * stations that group by order, one button moves the ticket's items. Every
 * tap sends the status the screen showed, so a second screen never skips a
 * step. Recall lists the last moves with Undo; voided items stay visible
 * for a few minutes. Refreshes on realtime events and every 30 s.
 *
 * Dispatch / expo stations ("Wait for the whole order", api/dispatch.py)
 * show each order from the moment it is sent, with the items still cooking
 * dimmed; the button works once everything arrived. A step that asks who
 * delivers opens the driver picker first.
 */

const API = "renpos.api.kitchen";
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

function beep() {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    const ctx = new Ctx();
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.frequency.value = 880;
    g.gain.setValueAtTime(0.2, ctx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
    o.connect(g); g.connect(ctx.destination);
    o.start(); o.stop(ctx.currentTime + 0.4);
    o.onended = () => ctx.close();
  } catch { /* no audio */ }
}

function timeOf(value) {
  const t = frappe.datetime?.str_to_obj ? frappe.datetime.str_to_obj(value) : new Date(value);
  return t.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** Who takes it: a driver of the restaurant, or a name typed in. Resolves null when cancelled. */
function askDriver(station) {
  return new Promise((resolve) => {
    frappe.call({ method: "renpos.api.dispatch.drivers", args: { station } }).then((r) => {
      const list = r.message || [];
      let done = false;
      const d = new frappe.ui.Dialog({
        title: __("Who delivers it?"),
        fields: [
          ...(list.length ? [{
            fieldtype: "Select", fieldname: "driver", label: __("Driver"),
            options: [{ value: "", label: "" }, ...list.map((x) => ({ value: x.user, label: x.full_name }))],
          }] : []),
          { fieldtype: "Data", fieldname: "driver_name", label: list.length ? __("Or another name") : __("Driver name"),
            description: list.length ? "" : __("Give the drivers a role with \"Delivers orders\" to pick them from a list.") },
        ],
        primary_action_label: __("Dispatch"),
        primary_action: (v) => {
          if (!v.driver && !(v.driver_name || "").trim()) { frappe.msgprint(__("Choose who delivers it")); return; }
          done = true;
          d.hide();
          resolve({ driver: v.driver || "", driver_name: v.driver ? "" : (v.driver_name || "").trim() });
        },
      });
      d.onhide = () => { if (!done) resolve(null); };
      d.show();
    }, () => resolve(null));
  });
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
  const [recall, setRecall] = useState(null); // null = closed, [] = list
  const [sound, setSound] = useState(true);
  const known = useRef(null); // ticket keys already seen

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

  // a sound when a new ticket arrives
  useEffect(() => {
    if (!queue) return;
    const keys = new Set(queue.tickets.map((t) => t.key));
    if (known.current && sound && [...keys].some((k) => !known.current.has(k))) beep();
    known.current = keys;
  }, [queue, sound]);

  const loadRecall = useCallback(() => {
    return call("get_recent", { station: stationName }).then((r) => setRecall(r || []), () => setRecall([]));
  }, [stationName]);

  // realtime: orders sent to the kitchen, status changes, order edits
  useEffect(() => {
    if (!open) return;
    const handler = () => {
      clearTimeout(timer.current);
      timer.current = setTimeout(refresh, 400);
    };
    frappe.realtime.doctype_subscribe?.("Ren Order");
    // ren_config: the station's flow, item groups, rooms or the person's access changed
    const events = ["kitchen_order", "kitchen_update", "order_update", "ren_config"];
    events.forEach((e) => frappe.realtime.on(e, handler));
    return () => {
      clearTimeout(timer.current);
      events.forEach((e) => frappe.realtime.off(e, handler));
    };
  }, [open, refresh]);

  // args: {identifier} or {ticket}; expected = the status this screen shows
  const advance = async (key, args, expected, needsDriver = false) => {
    if (busy[key]) return;
    if (needsDriver) {
      const who = await askDriver(stationName);
      if (!who) return;
      args = { ...args, ...who };
    }
    setBusy((b) => ({ ...b, [key]: true }));
    try {
      await call("advance", { station: stationName, ...args, expected });
    } catch {
      // Frappe shows the server message (e.g. another screen moved it first)
    } finally {
      await refresh();
      if (recall) loadRecall();
      setBusy((b) => { const n = { ...b }; delete n[key]; return n; });
    }
  };

  const undo = async (log) => {
    try {
      await call("undo", { station: stationName, log });
    } catch { /* message shown by Frappe */ }
    await Promise.all([refresh(), loadRecall()]);
  };

  if (!open) return null;

  const grouped = !!queue?.station?.group_items_by_order;
  const tickets = queue?.tickets || [];
  const voids = queue?.voids || [];

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
        <div className="flex items-center gap-1">
          <button onClick={() => setSound((v) => !v)} className="p-1.5 rounded-lg hover:bg-white/10"
            title={sound ? __("Mute new-ticket sound") : __("Sound on new tickets")}>
            {sound ? <Bell size={18} /> : <BellOff size={18} />}
          </button>
          <button onClick={() => (recall ? setRecall(null) : loadRecall())}
            className={`p-1.5 rounded-lg hover:bg-white/10 ${recall ? "bg-white/10" : ""}`} title={__("Recall")}>
            <History size={18} />
          </button>
          <button onClick={refresh} className="p-1.5 rounded-lg hover:bg-white/10" title={__("Refresh")}>
            <RotateCw size={18} />
          </button>
        </div>
      )}
    >
      {!queue && !error && (
        <div className="flex justify-center py-24 text-muted-foreground"><Loader2 className="animate-spin" /></div>
      )}
      {error && <p className="p-6 text-rose-400">{error}</p>}

      {recall && (
        <section className="m-3 rounded-2xl border border-border bg-card">
          <header className="flex items-center gap-2 px-3 py-2 border-b border-border font-semibold">
            <History size={16} /> {__("Recall — last moves at this station")}
          </header>
          {recall.length === 0 && <p className="px-3 py-3 text-sm text-muted-foreground">{__("No recent moves.")}</p>}
          <ul className="divide-y divide-border max-h-72 overflow-auto">
            {recall.map((r) => (
              <li key={r.name} className="flex items-center gap-3 px-3 py-2 text-sm">
                <span className="tabular-nums text-muted-foreground w-12 shrink-0">{timeOf(r.changed_at)}</span>
                <span className="flex-1 min-w-0 truncate">
                  <b>{r.qty} × {r.item_name}</b> · {r.table} · {r.from_status} → {r.to_status}
                  <span className="text-muted-foreground"> · {r.user_name}</span>
                </span>
                {r.can_undo && (
                  <button onClick={() => undo(r.name)}
                    className="flex items-center gap-1 px-2.5 py-1 rounded-lg border border-border hover:bg-muted">
                    <Undo2 size={14} /> {__("Undo")}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {voids.length > 0 && (
        <section className="m-3 rounded-2xl border border-rose-500/50 bg-rose-500/10">
          <header className="flex items-center gap-2 px-3 py-2 font-bold text-rose-300">
            <Ban size={16} /> {__("Voided — stop preparing")}
          </header>
          <ul className="divide-y divide-rose-500/20">
            {voids.map((v) => (
              <li key={v.name} className="flex items-center gap-3 px-3 py-2 text-sm">
                <span className="tabular-nums text-rose-200/80 w-12 shrink-0">{timeOf(v.voided_at)}</span>
                <span className="flex-1 min-w-0">
                  <b className="line-through">{v.qty} × {v.item_name}</b>
                  {v.modifiers && <span className="text-rose-200/80"> · {v.modifiers}</span>}
                  <span> · {v.table_description}</span>
                </span>
                <span className="text-xs text-rose-200/90 text-right">
                  {v.reason}{v.note ? `: ${v.note}` : ""} · {v.voided_by_name}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
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
            <article key={t.key} className="rounded-2xl border border-border bg-card flex flex-col overflow-hidden">
              <header className="flex items-start justify-between gap-2 px-3 py-2.5 border-b border-border">
                <div className="min-w-0">
                  <p className="text-lg font-extrabold leading-tight truncate">
                    {t.table_description}
                    {t.round > 1 && (
                      <span className="ml-2 align-middle text-[11px] font-bold px-1.5 py-0.5 rounded bg-sky-500/20 text-sky-300">
                        {__("Round {0}", [t.round])}
                      </span>
                    )}
                  </p>
                  <p className="text-xs text-muted-foreground truncate">
                    {t.room_description} · #{t.short_name}{t.dinners ? ` · ${t.dinners} ${__("guests")}` : ""}
                    {t.server ? ` · ${t.server}` : ""}
                  </p>
                  {!!t.delivery && (
                    <p className="text-xs text-sky-300 truncate flex items-center gap-1" title={t.address}>
                      <Truck size={12} className="shrink-0" /> {t.address}
                      {t.deliver_by ? ` · ${timeOf(t.deliver_by)}` : ""}
                    </p>
                  )}
                  {t.driver && (
                    <p className="text-xs font-semibold text-violet-300 truncate">{__("Driver: {0}", [t.driver])}</p>
                  )}
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
                  <li key={i.identifier} className={i.waiting ? "opacity-45" : ""}>
                    <button
                      onClick={() => !grouped && advance(i.identifier, { identifier: i.identifier }, i.status, !!i.ask_driver)}
                      disabled={grouped || !i.next_status}
                      className={`w-full text-left px-3 py-2.5 flex items-start gap-3 ${grouped ? "cursor-default" : "hover:bg-muted/50 active:bg-muted"}`}
                    >
                      <span className="text-xl font-extrabold tabular-nums w-8 shrink-0">{i.qty}</span>
                      <span className="flex-1 min-w-0">
                        <span className="block font-semibold leading-snug">{i.item_name}</span>
                        {i.modifiers?.length > 0 && (
                          <span className="block text-sm font-medium text-sky-300">{i.modifiers.join(" · ")}</span>
                        )}
                        {i.notes && <span className="block text-xs italic text-amber-200/90">{i.notes}</span>}
                      </span>
                      <span className="shrink-0 flex flex-col items-end gap-1">
                        {busy[i.identifier]
                          ? <Loader2 size={16} className="animate-spin" />
                          : <StatusBadge status={i.status} message={i.message} color={i.color} />}
                        {!grouped && i.next_status && (
                          <span className="text-[10px] text-muted-foreground">→ {i.action || i.next_status}</span>
                        )}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>

              {!!t.whole_order && !t.ready && (
                <div className="m-2 py-2.5 rounded-xl border border-dashed border-border text-muted-foreground text-sm font-semibold flex items-center justify-center gap-2">
                  <Hourglass size={15} />
                  {__("Waiting for the kitchen · {0} of {1} ready", [t.total_items - t.waiting_items, t.total_items])}
                </div>
              )}
              {grouped && t.next_status && (
                <button
                  onClick={() => advance(t.key, { ticket: t.key }, t.status, !!t.ask_driver)}
                  disabled={!!busy[t.key]}
                  className="m-2 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold flex items-center justify-center gap-2"
                >
                  {busy[t.key] ? <Loader2 size={16} className="animate-spin" /> : t.ask_driver ? <Truck size={16} /> : null}
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
