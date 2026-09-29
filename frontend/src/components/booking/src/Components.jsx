import {
  Users, Clock, CalendarDays,
  ChevronRight, Check, Armchair,
} from "lucide-react";
import { motion } from "framer-motion";
import { StatusBadge } from "./StatusBadge";

export function Field({ label, required, icon: Icon, error, children, className = "" }) {
  return (
    <div className={`space-y-1.5 ${className}`}>
      {label && (
        <label className="flex items-center gap-1.5 text-xs font-medium text-zinc-400">
          {Icon && <Icon size={12} className="text-zinc-500" />}
          {label}
          {required && <span className="text-amber-500">*</span>}
        </label>
      )}
      {children}
      {error && <p className="text-[11px] text-rose-400">{error}</p>}
    </div>
  );
}

export function Input({ className = "", ...props }) {
  return (
    <input
      className={`
        w-full h-9 px-3 rounded-lg text-sm
        border border-zinc-700/50
        focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/20
        transition-all duration-200
        disabled:opacity-50 disabled:cursor-not-allowed
        ${className}
      `}
      {...props}
    />
  );
}

export function Select({ options, className = "", ...props }) {
  return (
    <select
      className={`
        w-full h-9 px-3 rounded-lg text-sm
        border border-zinc-700/50
        focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/20
        transition-all duration-200
        ${className}
      `}
      {...props}
    >
      {options.map(opt => (
        <option key={opt.value} value={opt.value} disabled={opt.disabled}>
          {opt.label}
        </option>
      ))}
    </select>
  );
}

// ─── Table Card (for visual selection) ───────────────────
export function TableCard({ table, selected, onClick }) {
  const available = table.available;
  const isSelected = selected === table.name;
  const indicator = table.status_indicator;

  return (
    <motion.button
      layout
      whileHover={available ? { scale: 1.03 } : {}}
      whileTap={available ? { scale: 0.97 } : {}}
      onClick={() => available && onClick(table)}
      disabled={!available}
      className={`
        relative p-3 rounded-xl border-2 text-left transition-all duration-200
        ${isSelected
          ? "border-amber-500 bg-amber-500/10 shadow-lg shadow-amber-500/10"
          : available
            ? "border-zinc-700/50 bg-zinc-800/50 hover:border-zinc-600 hover:bg-zinc-800"
            : "border-zinc-800/50 bg-zinc-900/50 opacity-50 cursor-not-allowed"
        }
      `}
    >
      {/* Availability dot */}
      <div className={`absolute top-2 right-2 w-2 h-2 rounded-full ${
        indicator === "green" ? "bg-emerald-400" :
        indicator === "red" ? "bg-rose-400" :
        "bg-zinc-600"
      }`} />

      {/* Table name */}
      <div className="text-base font-semibold text-zinc-200 mb-1">
        {table.table_name || table.name}
      </div>

      {/* Capacity */}
      <div className="flex items-center gap-1 text-xs text-zinc-500">
        <Users size={11} />
        <span>{table.capacity} seats</span>
      </div>

      {/* Conflict info */}
      {table.conflict_info && (
        <div className="mt-2 text-[10px] text-rose-400/80 truncate">
          {table.conflict_info}
        </div>
      )}

      {/* Selected checkmark */}
      {isSelected && (
        <motion.div
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-amber-500 flex items-center justify-center"
        >
          <Check size={11} className="text-zinc-900" />
        </motion.div>
      )}
    </motion.button>
  );
}

// ─── Search Result Card ──────────────────────────────────
export function BookingResultCard({ booking, onSelect }) {
  return (
    <motion.button
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      onClick={() => onSelect(booking)}
      className="w-full p-3 rounded-xl border border-zinc-700/50 hover:bg-zinc-800 hover:border-zinc-600 transition-all text-left group"
    >
      <div className="flex items-start justify-between mb-2">
        <div>
          <div className="text-sm font-semibold text-zinc-200">
            {booking.customer_name || booking.guest_name}
          </div>
          <div className="text-xs text-zinc-500 mt-0.5">{booking.name}</div>
        </div>
        <StatusBadge status={booking.status} />
      </div>
      <div className="flex items-center gap-3 text-xs text-zinc-400">
        <span className="flex items-center gap-1">
          <CalendarDays size={11} />
          {booking.reservation_date}
        </span>
        <span className="flex items-center gap-1">
          <Clock size={11} />
          {String(booking.reservation_time).substring(0, 5)}
        </span>
        <span className="flex items-center gap-1">
          <Users size={11} />
          {booking.party_size}
        </span>
        {booking.table && (
          <span className="flex items-center gap-1">
            <Armchair size={11} />
            {booking.table}
          </span>
        )}
      </div>
      <div className="flex justify-end mt-2">
        <ChevronRight size={14} className="text-zinc-600 group-hover:text-amber-400 transition-colors" />
      </div>
    </motion.button>
  );
}