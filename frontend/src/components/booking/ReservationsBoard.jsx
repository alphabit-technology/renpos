import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import {
  CalendarDays, ChevronLeft, ChevronRight, Plus, Search, Users, Armchair, Clock, Loader2, MoreVertical,
  UserCheck, Ban, Undo2, Check, Pencil, Bell, ListOrdered, GanttChart, BookOpen, Star, AlertTriangle, X,
} from "lucide-react";
import Modal from "@c/ui/Modal";
import { StatusBadge } from "./src/StatusBadge";
import ReservationForm from "./Booking";
import { getUrlParam, setUrlParams } from "@/utils/urlState";
import { callWithApproval } from "@/utils/approval";

/**
 * ReservationsBoard — the host stand.
 *
 * One day at a time: reservations (late ones flagged, with the guest's
 * history and notes), the waitlist and a timeline of every table. From here
 * the host seats a party (on its table or another one, opening the table's
 * order), marks no-shows, cancels or reinstates, edits, and texts waiting
 * parties that their table is ready. Refreshes in real time.
 */

const API = "renpos.api.booking";

function call(method, args = {}) {
  return callWithApproval(`${API}.${method}`, args);
}

// a datetime ("2026-10-01 19:30:00") or a time ("9:30:00") -> "19:30" / "09:30"
const timeOf = (dt) => {
  if (!dt) return "";
  const s = String(dt);
  const t = s.includes(" ") ? s.split(" ")[1] : s;
  const [h, m] = t.split(":");
  return `${String(h).padStart(2, "0")}:${String(m || "0").padStart(2, "0")}`;
};
const hhmm = timeOf;
const minutesOf = (dt, day) => {
  const d = frappe.datetime.str_to_obj(String(dt));
  const base = frappe.datetime.str_to_obj(`${day} 00:00:00`);
  return Math.round((d - base) / 60000);
};
const shiftDay = (day, n) => frappe.datetime.add_days(day, n);

export function ReservationsBoard({ open, onClose }) {
  const [day, setDay] = useState(() => frappe.datetime.get_today());
  const [data, setData] = useState(null);
  // the board's tab survives a reload (?view=wait | timeline)
  const [tab, setTabState] = useState(() => getUrlParam("view") || "list");
  const setTab = (t) => { setTabState(t); setUrlParams({ view: t === "list" ? null : t }); };
  const [query, setQuery] = useState("");
  const [form, setForm] = useState(null); // {booking?} | null
  const [seating, setSeating] = useState(null); // booking being seated without a free table
  const [busy, setBusy] = useState({});
  const [waitForm, setWaitForm] = useState(false);
  const timer = useRef(null);

  const load = useCallback(() => {
    return call("get_day", { date: day }).then(setData, () => setData({ bookings: [], tables: [], summary: {} }));
  }, [day]);

  useEffect(() => {
    if (!open) return undefined;
    let cancelled = false;
    call("get_day", { date: day }).then((d) => { if (!cancelled) setData(d); });
    const poll = setInterval(load, 60000);
    return () => { cancelled = true; clearInterval(poll); };
  }, [open, day, load]);

  // realtime: any reservation change
  useEffect(() => {
    if (!open) return undefined;
    const handler = () => { clearTimeout(timer.current); timer.current = setTimeout(load, 300); };
    frappe.realtime.on("booking_update", handler);
    return () => { clearTimeout(timer.current); frappe.realtime.off("booking_update", handler); };
  }, [open, load]);

  const act = async (b, method, args = {}, msg) => {
    if (busy[b.name]) return null;
    setBusy((x) => ({ ...x, [b.name]: true }));
    try {
      const res = await call(method, { booking_name: b.name, ...args });
      if (msg) frappe.show_alert({ message: msg, indicator: "green" });
      await load();
      return res;
    } catch {
      return null; // Frappe shows the server message
    } finally {
      setBusy((x) => { const n = { ...x }; delete n[b.name]; return n; });
    }
  };

  const busyTables = useMemo(() => new Set(data?.busy_tables || []), [data]);

  const seat = (b) => {
    const tables = [b.table, ...(b.extra_tables || [])].filter(Boolean);
    if (tables.length && !tables.some((t) => busyTables.has(t))) {
      act(b, "check_in_reservation", {}, __("{0} seated — the table's order is open", [b.customer_name || b.guest_name]));
    } else {
      setSeating(b);
    }
  };

  const bookings = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (data?.bookings || []).filter((b) => !q
      || [b.customer_name, b.guest_name, b.contact_number, b.name].some((v) => (v || "").toLowerCase().includes(q)));
  }, [data, query]);

  const tableName = useCallback((n) => (data?.tables || []).find((t) => t.name === n)?.table_name || n, [data]);

  if (!open) return null;

  const s = data?.summary || {};
  const reservations = bookings.filter((b) => b.status !== "Waitlisted");
  const waitlist = bookings.filter((b) => b.status === "Waitlisted");
  const groups = [
    [__("Upcoming"), reservations.filter((b) => ["Open", "Confirmed"].includes(b.status))],
    [__("Seated"), reservations.filter((b) => b.status === "Seated")],
    [__("Finished"), reservations.filter((b) => ["Completed", "No Show", "Cancelled"].includes(b.status))],
  ];

  const title = (
    <div className="flex items-center gap-2 min-w-0">
      <BookOpen size={20} className="shrink-0" />
      <span>{__("Reservations")}</span>
    </div>
  );

  return (
    <Modal open={open} onClose={onClose} size="full" title={title}>
      {/* toolbar */}
      <div className="flex flex-wrap items-center gap-2 px-3 py-2 border-b border-border">
        <div className="flex items-center gap-1">
          <button onClick={() => setDay((d) => shiftDay(d, -1))} className="p-2 rounded-lg hover:bg-muted"><ChevronLeft size={16} /></button>
          <label className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-muted/50 text-sm font-semibold cursor-pointer">
            <CalendarDays size={15} />
            <span>{day === frappe.datetime.get_today() ? __("Today") : frappe.datetime.str_to_user(day)}</span>
            <input type="date" value={day} onChange={(e) => e.target.value && setDay(e.target.value)} className="sr-only" />
          </label>
          <button onClick={() => setDay((d) => shiftDay(d, 1))} className="p-2 rounded-lg hover:bg-muted"><ChevronRight size={16} /></button>
          {day !== frappe.datetime.get_today() && (
            <button onClick={() => setDay(frappe.datetime.get_today())} className="px-2 py-1 text-xs rounded-lg hover:bg-muted">{__("Today")}</button>
          )}
        </div>

        <div className="flex items-center gap-3 text-xs text-muted-foreground px-2">
          <span><b className="text-foreground">{s.reservations || 0}</b> {__("reservations")}</span>
          <span><b className="text-foreground">{s.covers || 0}</b> {__("covers")}</span>
          <span><b className="text-foreground">{s.seated || 0}</b> {__("seated")}</span>
          <span><b className="text-foreground">{s.waiting || 0}</b> {__("waiting")}</span>
          {s.no_shows > 0 && <span className="text-rose-400"><b>{s.no_shows}</b> {__("no-shows")}</span>}
        </div>

        <div className="relative ml-auto">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={__("Name, phone, ID")}
            className="h-9 pl-8 pr-3 rounded-lg bg-muted/50 text-sm w-44 focus:outline-none" />
        </div>
        <button onClick={() => setWaitForm(true)}
          className="flex items-center gap-1.5 h-9 px-3 rounded-lg border border-border text-sm hover:bg-muted">
          <ListOrdered size={15} /> {__("Waitlist")}
        </button>
        <button onClick={() => setForm({})}
          className="flex items-center gap-1.5 h-9 px-3 rounded-lg bg-primary text-primary-foreground text-sm font-semibold">
          <Plus size={15} /> {__("Reservation")}
        </button>
      </div>

      {/* tabs */}
      <div className="flex gap-1 px-3 pt-2">
        {[["list", __("Reservations"), ListOrdered], ["wait", __("Waitlist") + (waitlist.length ? ` (${waitlist.length})` : ""), Users],
          ["timeline", __("Timeline"), GanttChart]].map(([k, label, Icon]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm ${tab === k ? "bg-muted font-semibold" : "text-muted-foreground hover:bg-muted/50"}`}>
            <Icon size={14} /> {label}
          </button>
        ))}
      </div>

      <div className="p-3">
        {!data && <div className="flex justify-center py-20"><Loader2 className="animate-spin" /></div>}

        {data && tab === "list" && (
          reservations.length === 0
            ? <Empty text={__("No reservations for this day.")} />
            : groups.map(([label, rows]) => rows.length > 0 && (
              <section key={label} className="mb-4">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">{label} · {rows.length}</h3>
                <div className="rounded-xl border border-border divide-y divide-border">
                  {rows.map((b) => (
                    <BookingRow key={b.name} b={b} busy={!!busy[b.name]} tableName={tableName} sms={!!data.policy?.sms}
                      onSeat={() => seat(b)} onEdit={() => setForm({ booking: b })} act={act} />
                  ))}
                </div>
              </section>
            ))
        )}

        {data && tab === "wait" && (
          waitlist.length === 0
            ? <Empty text={__("Nobody waiting. Add walk-ins with the Waitlist button.")} />
            : (
              <div className="rounded-xl border border-border divide-y divide-border">
                {waitlist.map((b, i) => (
                  <BookingRow key={b.name} b={b} position={i + 1} now={data.now} busy={!!busy[b.name]} tableName={tableName}
                    sms={!!data.policy?.sms} onSeat={() => seat(b)} onEdit={() => setForm({ booking: b })} act={act} />
                ))}
              </div>
            )
        )}

        {data && tab === "timeline" && (
          <Timeline data={data} day={day} onPick={(b) => (["Open", "Confirmed", "Waitlisted", "No Show"].includes(b.status) ? seat(b) : setForm({ booking: b }))} />
        )}
      </div>

      {form && (
        <ReservationForm open booking={form.booking || null} defaults={{ reservation_date: day }}
          onClose={() => setForm(null)} onSuccess={load} />
      )}
      {seating && (
        <SeatDialog booking={seating} busyTables={busyTables} onClose={() => setSeating(null)}
          onSeat={async (table) => {
            const res = await act(seating, "check_in_reservation", { table },
              __("{0} seated — the table's order is open", [seating.customer_name || seating.guest_name]));
            if (res) setSeating(null);
          }} />
      )}
      {waitForm && <WaitlistDialog onClose={() => setWaitForm(false)} onDone={() => { setWaitForm(false); setTab("wait"); load(); }} />}
    </Modal>
  );
}

function Empty({ text }) {
  return <div className="flex flex-col items-center gap-2 py-16 text-muted-foreground"><BookOpen size={32} /><p className="text-sm">{text}</p></div>;
}

function GuestBadges({ g }) {
  if (!g) return null;
  const tags = (g.tags || "").split(",").map((t) => t.trim()).filter(Boolean);
  return (
    <span className="flex flex-wrap items-center gap-1">
      {tags.map((t) => (
        <span key={t} className="px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300 text-[10px] font-semibold flex items-center gap-0.5">
          {/vip/i.test(t) && <Star size={9} fill="currentColor" />}{t}
        </span>
      ))}
      {g.visits > 0 && <span className="text-[10px] text-muted-foreground">{__("{0} visits", [g.visits])}</span>}
      {g.no_shows > 0 && <span className="text-[10px] text-rose-400 font-semibold">{__("{0} no-shows", [g.no_shows])}</span>}
    </span>
  );
}

function BookingRow({ b, position, now, busy, tableName, sms, onSeat, onEdit, act }) {
  const [menu, setMenu] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!menu) return undefined;
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setMenu(false); };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [menu]);

  const tables = [b.table, ...(b.extra_tables || [])].filter(Boolean).map(tableName).join(" + ");
  const name = b.customer_name || b.guest_name;
  const canSeat = ["Open", "Confirmed", "Waitlisted", "No Show"].includes(b.status);
  // minutes waiting, by the server clock of the last refresh
  const waitedMin = b.status === "Waitlisted" && b.creation && now
    ? Math.max(0, Math.round((frappe.datetime.str_to_obj(String(now)) - frappe.datetime.str_to_obj(String(b.creation))) / 60000)) : null;
  const item = (icon, label, onClick, cls = "") => {
    const Icon = icon;
    return (
      <button onClick={() => { setMenu(false); onClick(); }}
        className={`w-full flex items-center gap-2 px-3 py-1.5 text-xs hover:bg-accent ${cls}`}>
        <Icon size={13} /> {label}
      </button>
    );
  };

  return (
    <div className={`flex items-center gap-3 px-3 py-2.5 ${b.late ? "bg-rose-500/5" : ""}`}>
      <div className="w-14 shrink-0 text-center">
        {position ? (
          <><p className="text-lg font-extrabold">#{position}</p><p className="text-[10px] text-muted-foreground">{waitedMin}′</p></>
        ) : (
          <><p className="text-base font-bold tabular-nums">{timeOf(b.reservation_time)}</p>
            {b.late && <p className="text-[10px] font-bold text-rose-400 flex items-center justify-center gap-0.5"><AlertTriangle size={10} />{__("Late")}</p>}</>
        )}
      </div>
      <div className="flex-1 min-w-0">
        <p className="font-semibold truncate flex items-center gap-2">
          {name}
          <span className="flex items-center gap-0.5 text-xs font-normal text-muted-foreground"><Users size={12} />{b.party_size}</span>
        </p>
        <div className="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
          {tables && <span className="flex items-center gap-0.5"><Armchair size={11} />{tables}</span>}
          {b.contact_number && <span>{b.contact_number}</span>}
          {b.quoted_wait > 0 && <span>{__("quoted {0} min", [b.quoted_wait])}</span>}
          {b.notified_at && <span className="text-emerald-400">{__("notified {0}", [hhmm(b.notified_at)])}</span>}
          <GuestBadges g={b.guest} />
        </div>
        {(b.notes || b.guest?.guest_notes) && (
          <p className="text-xs text-amber-200/90 truncate">{[b.notes, b.guest?.guest_notes].filter(Boolean).join(" · ")}</p>
        )}
      </div>
      <StatusBadge status={b.status} />
      <div className="flex items-center gap-1 shrink-0" ref={ref}>
        {busy && <Loader2 size={16} className="animate-spin" />}
        {canSeat && (
          <button onClick={onSeat} disabled={busy}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold">
            <UserCheck size={14} /> {__("Seat")}
          </button>
        )}
        {b.status === "Waitlisted" && sms && b.contact_number && (
          <button onClick={() => act(b, "notify_table_ready", {}, __("Message sent"))} disabled={busy}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-border text-xs hover:bg-muted" title={__("Text: table ready")}>
            <Bell size={14} />
          </button>
        )}
        <div className="relative">
          <button onClick={() => setMenu((v) => !v)} className="p-1.5 rounded-lg hover:bg-muted"><MoreVertical size={16} /></button>
          {menu && (
            <div className="absolute right-0 top-full mt-1 z-50 w-44 rounded-lg bg-popover border border-border shadow-xl py-1">
              {!["Completed"].includes(b.status) && item(Pencil, __("Edit"), onEdit)}
              {b.status === "Seated" && item(Check, __("Complete"), () => act(b, "complete_reservation", {}, __("Completed")))}
              {["Open", "Confirmed"].includes(b.status) && item(X, __("No Show"), () => act(b, "mark_no_show"), "text-rose-400")}
              {["Cancelled", "No Show"].includes(b.status) && item(Undo2, __("Reinstate"), () => act(b, "set_status", { status: b.table ? "Confirmed" : "Open" }))}
              {["Open", "Confirmed", "Waitlisted"].includes(b.status) && item(Ban, __("Cancel"), () => {
                frappe.prompt({ fieldname: "reason", fieldtype: "Data", label: __("Reason") },
                  (v) => act(b, "cancel_reservation", { reason: v.reason }, __("Cancelled")), __("Cancel reservation"), __("Cancel it"));
              }, "text-rose-400")}
              {item(BookOpen, __("Open record"), () => frappe.set_route("Form", "Ren Booking", b.name))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function SeatDialog({ booking, busyTables, onClose, onSeat }) {
  const [tables, setTables] = useState(null);
  const [table, setTable] = useState(null);
  useEffect(() => {
    const now = frappe.datetime.now_datetime();
    call("get_table_availability", {
      date: now.substring(0, 10), time_start: now.substring(11, 16), duration: booking.duration || 90,
      party_size: 0, exclude: booking.name,
    }).then((t) => setTables(t || []), () => setTables([]));
  }, [booking]);
  return (
    <Modal open size="md" onClose={onClose} title={__("Seat {0} ({1})", [booking.customer_name || booking.guest_name, booking.party_size])}>
      <div className="p-4 space-y-3">
        <p className="text-xs text-muted-foreground">{__("Choose a free table. The table's order opens with the party size.")}</p>
        {tables === null ? <div className="flex justify-center py-10"><Loader2 className="animate-spin" /></div> : (
          <div className="grid grid-cols-3 gap-2">
            {tables.map((t) => {
              const free = t.available && !busyTables.has(t.name);
              const small = Number(t.capacity) && Number(t.capacity) < booking.party_size;
              return (
                <button key={t.name} disabled={!free} onClick={() => setTable(t.name)}
                  className={`p-3 rounded-xl border-2 text-left ${table === t.name ? "border-amber-500 bg-amber-500/10"
                    : free ? "border-border hover:bg-muted" : "border-transparent opacity-40"}`}>
                  <p className="font-bold">{t.table_name}</p>
                  <p className={`text-xs ${small ? "text-amber-400" : "text-muted-foreground"}`}>{t.capacity || "?"} {__("seats")} · {t.room_name}</p>
                  {!free && <p className="text-[10px] text-rose-400 truncate">{t.conflict_info || __("Occupied")}</p>}
                </button>
              );
            })}
          </div>
        )}
      </div>
      <div className="px-4 py-3 border-t border-border flex justify-end gap-2">
        <button onClick={onClose} className="px-4 py-2 rounded-lg bg-muted text-sm">{__("Cancel")}</button>
        <button disabled={!table} onClick={() => onSeat(table)}
          className="px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm font-semibold disabled:opacity-50 flex items-center gap-1.5">
          <UserCheck size={15} /> {__("Seat here")}
        </button>
      </div>
    </Modal>
  );
}

function WaitlistDialog({ onClose, onDone }) {
  const [f, setF] = useState({ guest_name: "", contact_number: "", party_size: 2, quoted_wait: 15, notes: "" });
  const [saving, setSaving] = useState(false);
  const save = async () => {
    if (!f.guest_name.trim()) return;
    setSaving(true);
    try {
      await call("add_to_waitlist", f);
      onDone();
    } catch {
      setSaving(false);
    }
  };
  const inp = "w-full h-10 px-3 rounded-lg border border-border bg-transparent text-sm";
  return (
    <Modal open size="sm" onClose={onClose} title={__("Add to Waitlist")}>
      <div className="p-4 grid grid-cols-2 gap-3">
        <label className="col-span-2 text-xs">{__("Name")}<input autoFocus className={inp} value={f.guest_name} onChange={(e) => setF({ ...f, guest_name: e.target.value })} /></label>
        <label className="text-xs">{__("Phone")}<input type="tel" className={inp} value={f.contact_number} onChange={(e) => setF({ ...f, contact_number: e.target.value })} /></label>
        <label className="text-xs">{__("Guests")}<input type="number" min={1} className={inp} value={f.party_size} onChange={(e) => setF({ ...f, party_size: parseInt(e.target.value, 10) || 1 })} /></label>
        <label className="text-xs">{__("Quoted wait (min)")}<input type="number" min={0} step={5} className={inp} value={f.quoted_wait} onChange={(e) => setF({ ...f, quoted_wait: parseInt(e.target.value, 10) || 0 })} /></label>
        <label className="text-xs">{__("Notes")}<input className={inp} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></label>
      </div>
      <div className="px-4 py-3 border-t border-border flex justify-end gap-2">
        <button onClick={onClose} className="px-4 py-2 rounded-lg bg-muted text-sm">{__("Cancel")}</button>
        <button onClick={save} disabled={saving || !f.guest_name.trim()} className="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-semibold disabled:opacity-50">
          {__("Add")}
        </button>
      </div>
    </Modal>
  );
}

const STATUS_BAR = {
  Open: "bg-amber-500/70", Confirmed: "bg-emerald-600/80", Seated: "bg-sky-600/80", Completed: "bg-zinc-600/70",
  "No Show": "bg-rose-600/60", Cancelled: "bg-zinc-700/40 line-through", Waitlisted: "bg-purple-600/60",
};

function TimelineRow({ label, sub, rows, day, from, to, onPick }) {
  const pct = (m) => `${((m - from) / (to - from)) * 100}%`;
  return (
    <div className="flex items-stretch border-b border-border min-h-[38px]">
      <div className="w-28 shrink-0 px-2 py-1.5 border-r border-border">
        <p className="text-sm font-semibold truncate">{label}</p>
        {sub && <p className="text-[10px] text-muted-foreground truncate">{sub}</p>}
      </div>
      <div className="relative flex-1">
        {rows.map((b) => {
          const s = Math.max(from, minutesOf(b.starts_at, day));
          const e = Math.min(to, minutesOf(b.ends_at, day));
          return (
            <button key={b.name} onClick={() => onPick(b)} title={`${b.customer_name} · ${b.party_size} · ${timeOf(b.starts_at)}–${timeOf(b.ends_at)}`}
              style={{ left: pct(s), width: `calc(${pct(e)} - ${pct(s)})` }}
              className={`absolute top-1 bottom-1 rounded-md px-1.5 text-[11px] text-white text-left truncate ${STATUS_BAR[b.status] || ""} ${b.late ? "ring-2 ring-rose-500" : ""}`}>
              {b.customer_name} · {b.party_size}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function Timeline({ data, day, onPick }) {
  const bookings = data.bookings.filter((b) => b.starts_at && b.status !== "Cancelled");
  const mins = bookings.flatMap((b) => [minutesOf(b.starts_at, day), minutesOf(b.ends_at, day)]);
  const from = Math.max(0, Math.floor((Math.min(17 * 60, ...mins) - 30) / 60) * 60);
  const to = Math.min(30 * 60, Math.ceil((Math.max(23 * 60, ...mins) + 30) / 60) * 60);
  const span = to - from;
  const pct = (m) => `${((m - from) / span) * 100}%`;
  const hours = [];
  for (let h = from; h <= to; h += 60) hours.push(h);
  const nowMin = day === frappe.datetime.get_today() ? minutesOf(frappe.datetime.now_datetime(), day) : null;
  const byTable = {};
  bookings.forEach((b) => [b.table, ...(b.extra_tables || [])].filter(Boolean).forEach((t) => (byTable[t] = [...(byTable[t] || []), b])));
  const unassigned = bookings.filter((b) => !b.table);
  const rowProps = { day, from, to, onPick };

  return (
    <div className="rounded-xl border border-border overflow-x-auto">
      <div className="min-w-[760px]">
        <div className="flex border-b border-border text-[10px] text-muted-foreground">
          <div className="w-28 shrink-0 px-2 py-1 border-r border-border flex items-center gap-1"><Clock size={11} /> {__("Table")}</div>
          <div className="relative flex-1 h-6">
            {hours.map((h) => (
              <span key={h} style={{ left: pct(h) }} className="absolute top-1 -translate-x-1/2">{String(Math.floor(h / 60) % 24).padStart(2, "0")}:00</span>
            ))}
          </div>
        </div>
        <div className="relative">
          {data.tables.map((t) => <TimelineRow key={t.name} {...rowProps} label={t.table_name} sub={`${t.capacity || "?"} · ${t.room_name || ""}`} rows={byTable[t.name] || []} />)}
          {unassigned.length > 0 && <TimelineRow {...rowProps} label={__("No table")} rows={unassigned} />}
          {nowMin !== null && nowMin >= from && nowMin <= to && (
            <div className="absolute top-0 bottom-0 w-px bg-rose-500 pointer-events-none" style={{ left: `calc(7rem + (100% - 7rem) * ${(nowMin - from) / span})` }} />
          )}
        </div>
      </div>
    </div>
  );
}

export default ReservationsBoard;
