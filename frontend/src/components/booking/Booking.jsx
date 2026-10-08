import { useState, useEffect, useCallback, useRef } from "react";
import {
  Users, Clock, CalendarDays, Phone, Mail, MessageSquare, ChevronRight, ChevronLeft, Check, Ban,
  AlertCircle, Armchair, Loader2, User, Timer,
} from "lucide-react";
import Modal from "@c/ui/Modal";
import { callWithApproval } from "@/utils/approval";
import { StepIndicator } from "./src/SteepIndicator";
import { Field, Input, TableCard } from "./src/Components";

/**
 * ReservationForm — new reservation, or edit one (`booking`).
 *
 * The bookable times come from the server (api.booking.get_slots): the
 * restaurant's reservation hours, free tables that fit the party and the
 * kitchen pacing. The table time follows the restaurant's settings by
 * party size and can be changed. Tables can be combined for big parties,
 * or left empty to assign one on arrival.
 */

const API = "renpos.api.booking";
const SOURCES = ["Phone", "Walk-in", "Online", "App"];

function call(method, args) {
  return callWithApproval(`${API}.${method}`, args);
}

// "9:00:00" / "09:00:00" / "09:00" -> "09:00"
function hhmm(t) {
  if (!t) return "";
  const [h, m] = String(t).split(":");
  return `${String(h).padStart(2, "0")}:${String(m || "0").padStart(2, "0")}`;
}

function addMinutes(time, minutes) {
  if (!time) return "";
  const [h, m] = time.split(":").map(Number);
  const total = (h * 60 + m + Number(minutes || 0)) % (24 * 60);
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

function initialForm(booking, defaults) {
  if (booking) {
    return {
      customer: booking.customer || "",
      customer_name: booking.customer ? booking.customer_name : "",
      guest_name: booking.guest_name || (booking.customer ? "" : booking.customer_name) || "",
      contact_number: booking.contact_number || "",
      email: booking.email || "",
      party_size: booking.party_size || 2,
      reservation_date: booking.reservation_date,
      reservation_time: hhmm(booking.reservation_time),
      duration: booking.duration || null,
      source: booking.source || "Phone",
      table: booking.table || "",
      extra_tables: booking.extra_tables || [],
      notes: booking.notes || "",
    };
  }
  return {
    customer: "", customer_name: "", guest_name: "", contact_number: "", email: "", party_size: 2,
    reservation_date: frappe.datetime.get_today(), reservation_time: "", duration: null, source: "Phone",
    table: "", extra_tables: [], notes: "", ...defaults,
  };
}

export default function ReservationForm({ open, onClose, onSuccess, booking = null, defaults = {} }) {
  const editing = !!booking;
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState({});
  const [form, setForm] = useState(() => initialForm(booking, defaults));
  const [policy, setPolicy] = useState(null);
  const [slots, setSlots] = useState(null);
  const [tables, setTables] = useState([]);
  const [tablesLoading, setTablesLoading] = useState(false);
  const [roomFilter, setRoomFilter] = useState("");

  const update = useCallback((field, value) => {
    setForm((prev) => ({ ...prev, [field]: value }));
    setErrors((prev) => ({ ...prev, [field]: null }));
  }, []);

  // restaurant rules: table time by party size, slot size
  useEffect(() => {
    call("get_policy_info").then(setPolicy, () => setPolicy({}));
  }, []);

  const autoDuration = (() => {
    if (!policy) return 90;
    const size = Number(form.party_size) || 1;
    const row = (policy.turn_times || []).find((r) => size >= r.min_party && size <= r.max_party);
    return row ? row.minutes : policy.default_duration || 90;
  })();
  const duration = form.duration || autoDuration;
  const endTime = addMinutes(form.reservation_time, duration);

  // bookable times for the date and party
  useEffect(() => {
    if (!form.reservation_date || !form.party_size) return;
    let cancelled = false;
    call("get_slots", { date: form.reservation_date, party_size: form.party_size, exclude: booking?.name }).then(
      (r) => { if (!cancelled) setSlots(r.slots || []); },
      () => { if (!cancelled) setSlots([]); }
    );
    return () => { cancelled = true; };
  }, [form.reservation_date, form.party_size, booking?.name]);

  // tables free for the chosen time, when the table step opens
  useEffect(() => {
    if (step !== 1 || !form.reservation_date || !form.reservation_time) return undefined;
    let cancelled = false;
    call("get_table_availability", {
      date: form.reservation_date, time_start: form.reservation_time, party_size: 0,
      duration, exclude: booking?.name,
    }).then(
      (t) => { if (!cancelled) { setTables(t || []); setTablesLoading(false); } },
      () => { if (!cancelled) { setTables([]); setTablesLoading(false); } }
    );
    return () => { cancelled = true; };
  }, [step, form.reservation_date, form.reservation_time, duration, booking?.name]);

  // Customer link (Frappe awesomplete)
  const customerRef = useRef(null);
  useEffect(() => {
    if (!customerRef.current || step !== 0) return undefined;
    const parent = $(customerRef.current).empty();
    const control = frappe.ui.form.make_control({
      df: {
        fieldtype: "Link", fieldname: "customer", options: "Customer", placeholder: __("Search customer..."),
        change() {
          const val = this.get_value();
          update("customer", val || "");
          if (!val) return;
          frappe.db.get_value("Customer", val, ["customer_name", "mobile_no", "email_id"]).then((r) => {
            const c = r.message || {};
            update("customer_name", c.customer_name || "");
            if (c.mobile_no) update("contact_number", c.mobile_no);
            if (c.email_id) update("email", c.email_id);
          });
        },
      },
      parent,
      render_input: true,
    });
    if (form.customer) control.set_value(form.customer);
    return () => parent.empty();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, update]);

  const seatsOf = (names) => names.reduce((a, n) => a + Number(tables.find((t) => t.name === n)?.capacity || 0), 0);
  const chosen = [form.table, ...form.extra_tables].filter(Boolean);
  const chosenSeats = seatsOf(chosen);

  const toggleTable = (t) => {
    if (!form.table) return update("table", t.name);
    if (form.table === t.name) {
      // the first combined table becomes the main one
      const [next, ...rest] = form.extra_tables;
      setForm((p) => ({ ...p, table: next || "", extra_tables: rest }));
      return;
    }
    const extra = form.extra_tables.includes(t.name)
      ? form.extra_tables.filter((x) => x !== t.name)
      : [...form.extra_tables, t.name];
    update("extra_tables", extra);
  };

  const validate = () => {
    const errs = {};
    if (step === 0) {
      if (!form.customer && !form.guest_name?.trim()) errs.guest_name = __("Guest name or customer is required");
      if (!form.party_size || form.party_size < 1) errs.party_size = __("At least 1 guest");
      if (!form.reservation_date) errs.reservation_date = __("Required");
      if (!form.reservation_time) errs.reservation_time = __("Pick a time");
      if (form.email && !/^\S+@\S+\.\S+$/.test(form.email)) errs.email = __("Invalid email");
    }
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const next = () => {
    if (!validate()) return;
    if (step === 0) setTablesLoading(true);
    setStep((s) => Math.min(s + 1, 2));
  };
  const back = () => setStep((s) => Math.max(s - 1, 0));

  const submit = async () => {
    setLoading(true);
    const args = {
      customer: form.customer, guest_name: form.customer ? "" : form.guest_name,
      contact_number: form.contact_number, email: form.email, party_size: form.party_size,
      reservation_date: form.reservation_date, reservation_time: form.reservation_time,
      duration: form.duration || 0, table: form.table, extra_tables: JSON.stringify(form.extra_tables),
      notes: form.notes, source: form.source,
    };
    try {
      const res = editing
        ? await call("update_reservation", { name: booking.name, ...args })
        : await call("create_reservation", args);
      frappe.show_alert({ message: editing ? __("Reservation updated") : __("Reservation created"), indicator: "green" });
      onSuccess?.(res);
      onClose?.();
    } catch {
      // Frappe shows the server message
    }
    setLoading(false);
  };

  const rooms = [...new Set(tables.map((t) => t.room_name).filter(Boolean))];
  const shownTables = roomFilter ? tables.filter((t) => t.room_name === roomFilter) : tables;
  const guestLabel = form.customer_name || form.guest_name || "—";

  return (
    <Modal size="md" open={open} onClose={onClose} title={editing ? __("Edit Reservation") : __("New Reservation")}>
      <div className="px-5 py-3 border-b border-border">
        <StepIndicator current={step} steps={[__("Guest & Time"), __("Table"), __("Confirm")]} />
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
        {step === 0 && (
          <div className="space-y-4">
            <div className="space-y-3">
              <Field label={__("Customer")} icon={User}>
                <div ref={customerRef} className="ren-link-control" />
              </Field>
              {!form.customer && (
                <Field label={__("Guest Name")} icon={User} error={errors.guest_name}>
                  <Input value={form.guest_name} onChange={(e) => update("guest_name", e.target.value)}
                    placeholder={__("Name for the reservation")} />
                </Field>
              )}
              <div className="grid grid-cols-2 gap-3">
                <Field label={__("Phone")} icon={Phone}>
                  <Input type="tel" value={form.contact_number} onChange={(e) => update("contact_number", e.target.value)} />
                </Field>
                <Field label={__("Email")} icon={Mail} error={errors.email}>
                  <Input type="email" value={form.email} onChange={(e) => update("email", e.target.value)}
                    placeholder={__("For the confirmation")} />
                </Field>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <Field label={__("Guests")} icon={Users} required error={errors.party_size}>
                <Input type="number" min={1} value={form.party_size}
                  onChange={(e) => update("party_size", parseInt(e.target.value, 10) || 1)} />
              </Field>
              <Field label={__("Date")} icon={CalendarDays} required error={errors.reservation_date}>
                <Input type="date" value={form.reservation_date} min={editing ? undefined : frappe.datetime.get_today()}
                  onChange={(e) => { update("reservation_date", e.target.value); update("reservation_time", ""); }} />
              </Field>
              <Field label={__("Table Time")} icon={Timer}>
                <div className="flex items-center gap-1">
                  <Input type="number" min={15} step={15} value={duration}
                    onChange={(e) => update("duration", parseInt(e.target.value, 10) || null)} />
                  <span className="text-xs text-muted-foreground">min</span>
                </div>
              </Field>
            </div>

            <Field label={__("Time")} icon={Clock} required error={errors.reservation_time}>
              {slots === null ? (
                <div className="py-3 flex justify-center"><Loader2 size={18} className="animate-spin" /></div>
              ) : slots.length === 0 ? (
                <p className="text-xs text-muted-foreground py-2">{__("No reservation hours on this day.")}</p>
              ) : (
                <div className="grid grid-cols-4 sm:grid-cols-6 gap-1.5 max-h-44 overflow-y-auto pr-1">
                  {slots.map((s) => {
                    const sel = form.reservation_time === s.time;
                    return (
                      <button key={s.time} type="button" title={s.available ? __("{0} tables free", [s.tables]) : s.reason}
                        onClick={() => update("reservation_time", s.time)}
                        className={`py-1.5 rounded-lg text-xs font-semibold tabular-nums border transition-colors ${
                          sel ? "bg-amber-500 text-black border-amber-500"
                            : s.available ? "border-border hover:bg-muted"
                              : "border-transparent text-muted-foreground/50 line-through"}`}>
                        {s.time}
                      </button>
                    );
                  })}
                </div>
              )}
              {form.reservation_time && (
                <p className="text-[11px] text-muted-foreground mt-1">
                  {__("Table held {0} – {1}", [form.reservation_time, endTime])}
                  {!(slots || []).find((s) => s.time === form.reservation_time)?.available && slots?.length > 0 && (
                    <span className="text-amber-400"> · {__("outside availability: a manager can still book it")}</span>
                  )}
                </p>
              )}
            </Field>

            <div className="flex gap-2">
              {SOURCES.map((s) => (
                <button key={s} type="button" onClick={() => update("source", s)}
                  className={`flex-1 py-2 rounded-lg text-xs font-medium border ${form.source === s
                    ? "bg-primary/40 border-amber-500/30" : "border-border hover:bg-muted"}`}>
                  {__(s)}
                </button>
              ))}
            </div>

            <Field label={__("Notes")} icon={MessageSquare}>
              <textarea rows={2} value={form.notes} onChange={(e) => update("notes", e.target.value)}
                placeholder={__("Allergies, occasion, seating requests...")}
                className="w-full px-3 py-2 rounded-lg border border-zinc-700/50 bg-transparent focus:outline-none focus:border-amber-500/50 resize-none" />
            </Field>
          </div>
        )}

        {step === 1 && (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-3 px-3 py-2.5 rounded-xl bg-muted/40 border border-border text-xs">
              <span className="flex items-center gap-1"><CalendarDays size={12} /> {form.reservation_date}</span>
              <span className="flex items-center gap-1"><Clock size={12} /> {form.reservation_time} – {endTime}</span>
              <span className="flex items-center gap-1"><Users size={12} /> {form.party_size}</span>
              {chosen.length > 0 && (
                <span className={`ml-auto font-semibold ${chosenSeats && chosenSeats < form.party_size ? "text-amber-400" : "text-emerald-400"}`}>
                  {__("{0} seats chosen", [chosenSeats])}
                </span>
              )}
            </div>
            <p className="text-[11px] text-muted-foreground">
              {__("Tap a table; tap more to combine them for a big party. You can also leave it without a table and assign one on arrival.")}
            </p>
            {rooms.length > 1 && (
              <div className="flex gap-1.5 overflow-x-auto pb-1">
                {["", ...rooms].map((r) => (
                  <button key={r || "all"} onClick={() => setRoomFilter(r)}
                    className={`shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium ${roomFilter === r ? "bg-muted" : "text-muted-foreground"}`}>
                    {r || __("All Rooms")}
                  </button>
                ))}
              </div>
            )}
            {tablesLoading ? (
              <div className="flex justify-center py-12"><Loader2 size={24} className="animate-spin" /></div>
            ) : (
              <div className="grid grid-cols-3 gap-2.5">
                {shownTables.map((t) => (
                  <TableCard key={t.name} table={t}
                    selected={chosen.includes(t.name) ? t.name : null}
                    onClick={toggleTable} />
                ))}
              </div>
            )}
          </div>
        )}

        {step === 2 && (
          <div className="rounded-xl border border-border overflow-hidden text-sm">
            <div className="px-4 py-3 border-b border-border">
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">{__("Guest")}</p>
              <p className="font-semibold">{guestLabel}</p>
              <p className="text-xs text-muted-foreground">{[form.contact_number, form.email].filter(Boolean).join(" · ")}</p>
            </div>
            <div className="grid grid-cols-2 divide-x divide-border">
              <div className="px-4 py-3">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">{__("When")}</p>
                <p>{frappe.datetime.str_to_user(form.reservation_date)}</p>
                <p className="text-xs text-muted-foreground">{form.reservation_time} – {endTime}</p>
              </div>
              <div className="px-4 py-3">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">{__("Party")}</p>
                <p>{__("{0} guests", [form.party_size])}</p>
                <p className="text-xs text-muted-foreground">{duration} min</p>
              </div>
            </div>
            <div className="px-4 py-3 border-t border-border flex items-center gap-2">
              <Armchair size={14} className="text-amber-400" />
              {chosen.length
                ? chosen.map((n) => tables.find((t) => t.name === n)?.table_name || n).join(" + ")
                : <span className="text-muted-foreground">{__("No table yet: assign it on arrival")}</span>}
            </div>
            {form.notes && <div className="px-4 py-3 border-t border-border text-xs">{form.notes}</div>}
            {!form.email && (
              <div className="px-4 py-2 border-t border-border text-[11px] text-muted-foreground flex items-center gap-1.5">
                <AlertCircle size={12} /> {__("No email: the guest won't get a confirmation")}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="px-5 py-4 border-t border-border flex items-center justify-between gap-3">
        <button onClick={step > 0 ? back : onClose}
          className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl text-xs font-medium bg-muted hover:bg-muted/70">
          {step > 0 ? <><ChevronLeft size={14} /> {__("Back")}</> : <><Ban size={14} /> {__("Cancel")}</>}
        </button>
        {step < 2 ? (
          <button onClick={next}
            className="flex items-center gap-1.5 px-6 py-2.5 rounded-xl text-xs font-semibold bg-primary text-primary-foreground">
            {step === 0 ? __("Choose Table") : chosen.length ? __("Review") : __("Continue without table")}
            <ChevronRight size={14} />
          </button>
        ) : (
          <button onClick={submit} disabled={loading}
            className="flex items-center gap-1.5 px-6 py-2.5 rounded-xl text-xs font-semibold text-black bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50">
            {loading ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
            {editing ? __("Save Changes") : __("Create Reservation")}
          </button>
        )}
      </div>
    </Modal>
  );
}
