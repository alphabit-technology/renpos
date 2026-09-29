import { useState, useEffect, useCallback, useRef } from "react";
import {
  X, Search, Users, Clock, CalendarDays, Phone, MessageSquare,
  ChevronRight, ChevronLeft, Check, Ban, AlertCircle, Armchair,
  Loader2, User, MapPin, Utensils, Timer, Coffee
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { format, parse, addMinutes, isToday, isBefore } from "date-fns";
import Modal from '@c/ui/Modal'
import { StatusBadge } from "./src/StatusBadge";
import { StepIndicator } from "./src/SteepIndicator";
import { Field, Input, Select, TableCard, BookingResultCard } from "./src/Components";
// ─── Status colors ───────────────────────────────────────


// ─── Duration options ────────────────────────────────────
const DURATIONS = [
  { value: 60, label: "1 hr" },
  { value: 90, label: "1.5 hr" },
  { value: 120, label: "2 hr" },
  { value: 150, label: "2.5 hr" },
  { value: 180, label: "3 hr" },
];

const SOURCES = ["Phone", "Walk-in", "Online", "App"];

// ─── Step indicator ──────────────────────────────────────


// ─── Status Badge ────────────────────────────────────────


// ─── Input Field ─────────────────────────────────────────


// ═════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═════════════════════════════════════════════════════════

export default function ReservationForm({
  restaurant,
  posProfile,
  open,
  onClose,
  onSuccess,
  // Optional: pre-fill for "click on table" flow
  defaults = {},
}) {
  // ─── State ─────────────────────────────────────
  const [mode, setMode] = useState("new"); // "new" | "search"
  const [step, setStep] = useState(0);     // 0: info, 1: table, 2: confirm
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState({});

  // Form data
  const [form, setForm] = useState({
    customer: "",
    customer_name: "",
    guest_name: "",
    contact_number: "",
    party_size: 2,
    reservation_date: format(new Date(), "yyyy-MM-dd"),
    reservation_time: format(addMinutes(new Date(), 30), "HH:mm"),
    duration: 120,
    source: "Phone",
    table: "",
    notes: "",
    ...defaults,
  });

  // Table selection
  const [tables, setTables] = useState([]);
  const [tablesLoading, setTablesLoading] = useState(false);
  const [roomFilter, setRoomFilter] = useState("");

  // Search mode
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [selectedBooking, setSelectedBooking] = useState(null);
  const [searchLoading, setSearchLoading] = useState(false);

  const searchTimeout = useRef(null);

  // ─── Computed ──────────────────────────────────
  const endTime = form.reservation_time
    ? format(addMinutes(parse(form.reservation_time, "HH:mm", new Date()), form.duration), "HH:mm")
    : "";

  const rooms = [...new Set(tables.map(t => t.room).filter(Boolean))];
  const filteredTables = roomFilter
    ? tables.filter(t => t.room === roomFilter)
    : tables;

  const selectedTable = tables.find(t => t.name === form.table);

  const stepLabels = mode === "new"
    ? ["Guest Info", "Select Table", "Confirm"]
    : ["Search", "Review", "Confirm"];

  // ─── Updater ───────────────────────────────────
  const updateForm = useCallback((field, value) => {
    setForm(prev => ({ ...prev, [field]: value }));
    setErrors(prev => ({ ...prev, [field]: null }));
  }, []);

  // ─── Fetch Tables ──────────────────────────────
  const fetchTables = useCallback(async () => {
    if (!form.reservation_date || !form.reservation_time) return;
    setTablesLoading(true);
    try {
      const r = await frappe.call({
        method: "restaurant_management.api.booking.get_table_availability",
        args: {
          //restaurant,
          date: form.reservation_date,
          time_start: form.reservation_time,
          time_end: endTime,
          party_size: form.party_size,
        },
      });
      setTables(r.message || []);
    } catch (e) {
      console.error("Failed to fetch tables", e);
      frappe.toast({ message: "Failed to load tables", indicator: "red" });
    }
    setTablesLoading(false);
  }, [form.reservation_date, form.reservation_time, form.party_size, endTime]);

  // ─── Search Reservations ───────────────────────
  const searchReservations = useCallback(async (query) => {
    if (!query || query.length < 2) {
      setSearchResults([]);
      return;
    }
    setSearchLoading(true);
    try {
      const r = await frappe.call({
        method: "restaurant_management.api.booking.search_reservation",
        args: { query, restaurant },
      });
      setSearchResults(r.message || []);
    } catch (e) {
      console.error("Search failed", e);
    }
    setSearchLoading(false);
  }, [restaurant]);

  // Debounced search
  useEffect(() => {
    if (mode !== "search") return;
    clearTimeout(searchTimeout.current);
    searchTimeout.current = setTimeout(() => searchReservations(searchQuery), 300);
    return () => clearTimeout(searchTimeout.current);
  }, [searchQuery, mode, searchReservations]);

  // ─── Validate step ────────────────────────────
  const validateStep = () => {
    const errs = {};

    if (mode === "new" && step === 0) {
      if (!form.customer && !form.guest_name) {
        errs.guest_name = "Guest name or customer is required";
      }
      if (!form.party_size || form.party_size < 1) {
        errs.party_size = "At least 1 guest";
      }
      if (!form.reservation_date) errs.reservation_date = "Required";
      if (!form.reservation_time) errs.reservation_time = "Required";
    }

    if (step === 1 && mode === "new") {
      if (!form.table) errs.table = "Please select a table";
    }

    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  // ─── Navigation ────────────────────────────────
  const nextStep = () => {
    if (!validateStep()) return;
    if (step === 1 && mode === "new") {
      // Moving to confirm — fetch tables if not loaded
    }
    setStep(s => Math.min(s + 1, 2));
  };

  const prevStep = () => setStep(s => Math.max(s - 1, 0));

  // When entering step 1 (table selection), load tables
  useEffect(() => {
    if (step === 1 && mode === "new") {
      fetchTables();
    }
  }, [step, mode, fetchTables]);

  // ─── Submit ────────────────────────────────────
  const handleSubmit = async () => {
    setLoading(true);
    try {
      if (mode === "new") {
        const r = await frappe.call({
          method: "restaurant_management.api.booking.create_reservation",
          args: {
            //restaurant,
            pos_profile: posProfile,
            customer: form.customer,
            customer_name: form.customer_name,
            guest_name: form.guest_name,
            contact_number: form.contact_number,
            party_size: form.party_size,
            reservation_date: form.reservation_date,
            reservation_time: form.reservation_time,
            duration: form.duration,
            table: form.table,
            notes: form.notes,
            source: form.source,
          },
        });
        frappe.toast({ message: "Reservation created!", indicator: "green" });
        onSuccess?.(r.message);
      } else if (selectedBooking) {
        // Check in existing reservation
        const r = await frappe.call({
          method: "restaurant_management.api.booking.check_in_reservation",
          args: { booking_name: selectedBooking.name },
        });
        frappe.toast({ message: "Guest checked in!", indicator: "green" });
        onSuccess?.(r.message);
      }
      onClose?.();
    } catch (e) {
      console.error("Submit failed", e);
      frappe.toast({
        message: e.message || "Something went wrong",
        indicator: "red",
      });
    }
    setLoading(false);
  };

  // ─── Select existing booking ───────────────────
  const handleSelectBooking = (booking) => {
    setSelectedBooking(booking);
    setForm(prev => ({
      ...prev,
      customer: booking.customer,
      customer_name: booking.customer_name,
      guest_name: booking.guest_name,
      contact_number: booking.contact_number,
      party_size: booking.party_size,
      reservation_date: booking.reservation_date,
      reservation_time: String(booking.reservation_time).substring(0, 5),
      duration: booking.duration || 120,
      table: booking.table || "",
      notes: booking.notes || "",
    }));
    setStep(1);
  };

  // ─── Customer Link (Frappe autocomplete) ───────
  const customerInputRef = useRef(null);
  useEffect(() => {
    if (!customerInputRef.current || mode !== "new") return;

    // Use Frappe's awesomplete for customer search
    const $input = $(customerInputRef.current);
    frappe.ui.form.make_control({
      df: {
        fieldtype: "Link",
        fieldname: "customer",
        options: "Customer",
        placeholder: "Search customer...",
        change: function () {
          const val = this.get_value();
          if (val) {
            updateForm("customer", val);
            frappe.db.get_value("Customer", val, ["customer_name", "mobile_no"])
              .then(r => {
                if (r.message) {
                  updateForm("customer_name", r.message.customer_name || "");
                  if (r.message.mobile_no) {
                    updateForm("contact_number", r.message.mobile_no);
                  }
                }
              });
          }else{
            updateForm("customer", "")
          }
        },
      },
      parent: $input.parent(),
      render_input: true,
    });
  }, [mode, updateForm]);

  // ═════════════════════════════════════════════════
  // RENDER
  // ═════════════════════════════════════════════════

  return (
    <Modal 
      size={"md"} open={open} onClose={onClose}
      title={mode === "new" ? "New Reservation" : "Find Reservation"}
    >
      <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-amber-500/10 flex items-center justify-center">
            <Utensils size={16} className="text-amber-400" />
          </div>
          <div>
            <StepIndicator current={step} steps={stepLabels} />
          </div>
        </div>
      </div>

      {/* ── Mode Toggle ── */}
      <div className="px-5 pt-4">
        <div className="flex gap-1 p-1 rounded-xl">
          <button
            onClick={() => { setMode("new"); setStep(0); setSelectedBooking(null); }}
            className={`flex-1 py-2 rounded-lg text-xs font-medium transition-all ${
              mode === "new"
                ? "bg-primary/60 text-zinc-100 shadow-sm"
                : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            <Coffee size={14} className="inline mr-1.5 -mt-0.5" />
            New Booking
          </button>
          <button
            onClick={() => { setMode("search"); setStep(0); }}
            className={`flex-1 py-2 rounded-lg text-xs font-medium transition-all ${
              mode === "search"
                ? "bg-primary/60 text-zinc-100 shadow-sm"
                : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            <Search size={14} className="inline mr-1.5 -mt-0.5" />
            I Have a Reservation
          </button>
        </div>
      </div>

      {/* ── Body ── */}
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
        <AnimatePresence mode="wait">
          {/* ═══ NEW BOOKING MODE ═══ */}
          {mode === "new" && step === 0 && (
            <motion.div
              key="new-step0"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="space-y-4"
            >
              {/* Customer / Guest */}
              <div className="space-y-3">
                <p className="text-[11px] font-medium text-zinc-500 uppercase tracking-wider">Guest Information</p>

                <Field label="Customer" icon={User}>
                  <div ref={customerInputRef}>
                    <Input
                      value={form.customer_name || form.customer}
                      onChange={e => updateForm("customer_name", e.target.value)}
                      placeholder="Search or type guest name..."
                    />
                  </div>
                </Field>

                {!form.customer && (
                  <Field label="Guest Name" icon={User} error={errors.guest_name}>
                    <Input
                      value={form.guest_name}
                      onChange={e => updateForm("guest_name", e.target.value)}
                      placeholder="Walk-in guest name"
                    />
                  </Field>
                )}

                <div className="grid grid-cols-2 gap-3">
                  <Field label="Phone" icon={Phone}>
                    <Input
                      type="tel"
                      value={form.contact_number}
                      onChange={e => updateForm("contact_number", e.target.value)}
                      placeholder="+504..."
                    />
                  </Field>
                  <Field label="Party Size" icon={Users} required error={errors.party_size}>
                    <Input
                      type="number"
                      min={1}
                      max={50}
                      value={form.party_size}
                      onChange={e => updateForm("party_size", parseInt(e.target.value) || 1)}
                    />
                  </Field>
                </div>
              </div>

              {/* Date & Time */}
              <div className="space-y-3">
                <p className="text-[11px] font-medium text-zinc-500 uppercase tracking-wider">When</p>

                <div className="grid grid-cols-2 gap-3">
                  <Field label="Date" icon={CalendarDays} required error={errors.reservation_date}>
                    <Input
                      type="date"
                      value={form.reservation_date}
                      onChange={e => updateForm("reservation_date", e.target.value)}
                      min={format(new Date(), "yyyy-MM-dd")}
                    />
                  </Field>
                  <Field label="Time" icon={Clock} required error={errors.reservation_time}>
                    <Input
                      type="time"
                      value={form.reservation_time}
                      onChange={e => updateForm("reservation_time", e.target.value)}
                    />
                  </Field>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <Field label="Duration" icon={Timer}>
                    <Select
                      value={form.duration}
                      onChange={e => updateForm("duration", parseInt(e.target.value))}
                      options={DURATIONS.map(d => ({ value: d.value, label: d.label }))}
                    />
                  </Field>
                  <Field label="End Time" icon={Clock}>
                    <div className="h-9 px-3 flex items-center rounded-lg text-zinc-400 border border-zinc-800">
                      {endTime || "—"}
                    </div>
                  </Field>
                </div>
              </div>

              {/* Source */}
              <div className="space-y-2">
                <p className="text-[11px] font-medium text-zinc-500 uppercase tracking-wider">Source</p>
                <div className="flex gap-2">
                  {SOURCES.map(s => (
                    <button
                      key={s}
                      onClick={() => updateForm("source", s)}
                      className={`
                        flex-1 py-2 rounded-lg text-xs font-medium transition-all
                        ${form.source === s
                          ? "bg-primary/40 border border-amber-500/30"
                          : "bg-secondary/50 text-secondary border border hover:bg-primary/10"}
                      `}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>

              {/* Notes */}
              <Field label="Notes" icon={MessageSquare}>
                <textarea
                  rows={2}
                  value={form.notes}
                  onChange={e => updateForm("notes", e.target.value)}
                  placeholder="Allergies, special requests..."
                  className="w-full px-3 py-2 rounded-lg placeholder-zinc-600 border border-zinc-700/50 focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/20 transition-all resize-none"
                />
              </Field>
            </motion.div>
          )}

          {/* ═══ TABLE SELECTION (step 1 — new mode) ═══ */}
          {mode === "new" && step === 1 && (
            <motion.div
              key="new-step1"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="space-y-4"
            >
              {/* Summary bar */}
              <div className="flex items-center gap-3 px-3 py-2.5 rounded-xl bg-zinc-800/50 border border-zinc-800 text-xs text-zinc-400">
                <span className="flex items-center gap-1">
                  <CalendarDays size={12} /> {form.reservation_date}
                </span>
                <span className="flex items-center gap-1">
                  <Clock size={12} /> {form.reservation_time} - {endTime}
                </span>
                <span className="flex items-center gap-1">
                  <Users size={12} /> {form.party_size}
                </span>
              </div>

              {/* Room filter */}
              {rooms.length > 1 && (
                <div className="flex gap-1.5 overflow-x-auto pb-1">
                  <button
                    onClick={() => setRoomFilter("")}
                    className={`shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                      !roomFilter
                        ? "bg-zinc-700 text-zinc-100"
                        : "bg-zinc-800/50 text-zinc-500 hover:text-zinc-300"
                    }`}
                  >
                    All Rooms
                  </button>
                  {rooms.map(room => (
                    <button
                      key={room}
                      onClick={() => setRoomFilter(room)}
                      className={`shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                        roomFilter === room
                          ? "bg-zinc-700 text-zinc-100"
                          : "bg-zinc-800/50 text-zinc-500 hover:text-zinc-300"
                      }`}
                    >
                      {room}
                    </button>
                  ))}
                </div>
              )}

              {/* Legend */}
              <div className="flex items-center gap-4 text-[11px] text-zinc-500">
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-400" /> Available</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-rose-400" /> Occupied</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-zinc-600" /> Too small</span>
              </div>

              {/* Table grid */}
              {tablesLoading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 size={24} className="animate-spin text-zinc-600" />
                </div>
              ) : filteredTables.length === 0 ? (
                <div className="text-center py-12 text-zinc-500 text-sm">
                  No tables found
                </div>
              ) : (
                <div className="grid grid-cols-3 gap-2.5">
                  {filteredTables.map(table => (
                    <TableCard
                      key={table.name}
                      table={table}
                      selected={form.table}
                      onClick={t => updateForm("table", t.name)}
                    />
                  ))}
                </div>
              )}

              {errors.table && (
                <p className="flex items-center gap-1 text-xs text-rose-400">
                  <AlertCircle size={12} /> {errors.table}
                </p>
              )}
            </motion.div>
          )}

          {/* ═══ CONFIRMATION (step 2 — new mode) ═══ */}
          {mode === "new" && step === 2 && (
            <motion.div
              key="new-step2"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="space-y-4"
            >
              <div className="rounded-xl border border-zinc-800 bg-zinc-800/30 overflow-hidden">
                {/* Guest */}
                <div className="px-4 py-3 border-b border-zinc-800/50">
                  <p className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Guest</p>
                  <p className="text-sm font-semibold text-zinc-100">
                    {form.customer_name || form.guest_name || "—"}
                  </p>
                  {form.contact_number && (
                    <p className="text-xs text-zinc-500 mt-0.5">{form.contact_number}</p>
                  )}
                </div>

                {/* Details grid */}
                <div className="grid grid-cols-2 divide-x divide-zinc-800/50">
                  <div className="px-4 py-3">
                    <p className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Date & Time</p>
                    <p className="text-sm text-zinc-200">{form.reservation_date}</p>
                    <p className="text-xs text-zinc-400">{form.reservation_time} — {endTime}</p>
                  </div>
                  <div className="px-4 py-3">
                    <p className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Party</p>
                    <p className="text-sm text-zinc-200">{form.party_size} guests</p>
                    <p className="text-xs text-zinc-400">{DURATIONS.find(d => d.value === form.duration)?.label}</p>
                  </div>
                </div>

                {/* Table */}
                <div className="px-4 py-3 border-t border-zinc-800/50">
                  <p className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Table</p>
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-lg bg-primary/50 flex items-center justify-center">
                      <Armchair size={14} className="text-amber-400" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-zinc-100">
                        {selectedTable?.table_name || form.table}
                      </p>
                      <p className="text-xs text-zinc-500">
                        {selectedTable?.capacity} seats
                        {selectedTable?.room && ` · ${selectedTable.room}`}
                      </p>
                    </div>
                  </div>
                </div>

                {/* Notes */}
                {form.notes && (
                  <div className="px-4 py-3 border-t border-zinc-800/50">
                    <p className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Notes</p>
                    <p className="text-xs text-zinc-300">{form.notes}</p>
                  </div>
                )}

                {/* Source */}
                <div className="px-4 py-3 border-t border-zinc-800/50 flex items-center justify-between">
                  <p className="text-[10px] uppercase tracking-wider text-zinc-500">Source</p>
                  <span className="text-xs text-zinc-400">{form.source}</span>
                </div>
              </div>
            </motion.div>
          )}

          {/* ═══ SEARCH MODE ═══ */}
          {mode === "search" && step === 0 && (
            <motion.div
              key="search-step0"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="space-y-4"
            >
              {/* Search input */}
              <div className="relative">
                <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
                <Input
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  placeholder="Search by name, phone, or booking ID..."
                  className="pl-10"
                  autoFocus
                />
                {searchLoading && (
                  <Loader2 size={14} className="absolute right-3 top-1/2 -translate-y-1/2 animate-spin text-zinc-500" />
                )}
              </div>

              {/* Results */}
              <div className="space-y-2">
                {searchResults.length > 0 ? (
                  searchResults.map(b => (
                    <BookingResultCard
                      key={b.name}
                      booking={b}
                      onSelect={handleSelectBooking}
                    />
                  ))
                ) : searchQuery.length >= 2 && !searchLoading ? (
                  <div className="text-center py-8 text-zinc-500 text-sm">
                    <Search size={24} className="mx-auto mb-2 opacity-30" />
                    No reservations found
                  </div>
                ) : (
                  <div className="text-center py-8 text-zinc-600 text-sm">
                    Type at least 2 characters to search
                  </div>
                )}
              </div>
            </motion.div>
          )}

          {/* ═══ SEARCH MODE — Review (step 1) ═══ */}
          {mode === "search" && step === 1 && selectedBooking && (
            <motion.div
              key="search-step1"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="space-y-4"
            >
              {/* Booking summary */}
              <div className="rounded-xl border border-zinc-800 bg-zinc-800/30 overflow-hidden">
                <div className="px-4 py-3 flex items-center justify-between border-b border-zinc-800/50">
                  <div>
                    <p className="text-sm font-semibold text-zinc-100">
                      {selectedBooking.customer_name || selectedBooking.guest_name}
                    </p>
                    <p className="text-xs text-zinc-500">{selectedBooking.name}</p>
                  </div>
                  <StatusBadge status={selectedBooking.status} />
                </div>

                <div className="grid grid-cols-2 divide-x divide-zinc-800/50">
                  <div className="px-4 py-3">
                    <p className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Reserved For</p>
                    <p className="text-sm text-zinc-200">{selectedBooking.reservation_date}</p>
                    <p className="text-xs text-zinc-400">
                      {String(selectedBooking.reservation_time).substring(0, 5)} — {String(selectedBooking.reservation_end_time).substring(0, 5)}
                    </p>
                  </div>
                  <div className="px-4 py-3">
                    <p className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Details</p>
                    <p className="text-sm text-zinc-200">{selectedBooking.party_size} guests</p>
                    {selectedBooking.table && (
                      <p className="text-xs text-zinc-400">Table: {selectedBooking.table}</p>
                    )}
                  </div>
                </div>

                {selectedBooking.notes && (
                  <div className="px-4 py-3 border-t border-zinc-800/50">
                    <p className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Notes</p>
                    <p className="text-xs text-zinc-300">{selectedBooking.notes}</p>
                  </div>
                )}
              </div>

              {/* Early arrival warning */}
              {selectedBooking.reservation_date === format(new Date(), "yyyy-MM-dd") && (
                <div className="flex items-start gap-2 p-3 rounded-xl bg-primary/50 border border-amber-500/20">
                  <AlertCircle size={16} className="text-amber-400 shrink-0 mt-0.5" />
                  <div className="text-xs text-amber-300">
                    <p className="font-medium">Check-in confirmation</p>
                    <p className="text-amber-400/70 mt-0.5">
                      Clicking confirm will mark this guest as seated at their assigned table.
                    </p>
                  </div>
                </div>
              )}

              {/* Not today warning */}
              {selectedBooking.reservation_date !== format(new Date(), "yyyy-MM-dd") && (
                <div className="flex items-start gap-2 p-3 rounded-xl bg-rose-500/10 border border-rose-500/20">
                  <AlertCircle size={16} className="text-rose-400 shrink-0 mt-0.5" />
                  <div className="text-xs text-rose-300">
                    <p className="font-medium">Reservation is not for today</p>
                    <p className="text-rose-400/70 mt-0.5">
                      This booking is for {selectedBooking.reservation_date}.
                      Do you want to check in the guest now?
                    </p>
                  </div>
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* ── Footer ── */}
      <div className="px-5 py-4 border-t border-zinc-800 flex items-center justify-between gap-3">
        {/* Back button */}
        {step > 0 ? (
          <button
            onClick={prevStep}
            className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl text-xs font-medium text-zinc-400 bg-zinc-800 hover:bg-zinc-700 transition-colors"
          >
            <ChevronLeft size={14} />
            Back
          </button>
        ) : (
          <button
            onClick={onClose}
            className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl text-xs font-medium text-zinc-400 bg-zinc-800 hover:bg-zinc-700 transition-colors"
          >
            <Ban size={14} />
            Cancel
          </button>
        )}

        {/* Action button */}
        {step < 2 && mode === "new" ? (
          <button
            onClick={nextStep}
            className="flex items-center gap-1.5 px-6 py-2.5 rounded-xl text-xs font-semibold text-zinc-900 bg-primary/50 hover:bg-amber-400 transition-colors shadow-lg shadow-amber-500/20"
          >
            {step === 0 ? "Select Table" : "Review"}
            <ChevronRight size={14} />
          </button>
        ) : mode === "search" && step === 0 ? (
          <div /> /* No action in search step 0 */
        ) : (
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="flex items-center gap-1.5 px-6 py-2.5 rounded-xl text-xs font-semibold text-zinc-900 bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 transition-colors shadow-lg shadow-emerald-500/20"
          >
            {loading ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Check size={14} />
            )}
            {mode === "new" ? "Create Reservation" : "Check In Guest"}
          </button>
        )}
      </div>
    </Modal>
  );
}