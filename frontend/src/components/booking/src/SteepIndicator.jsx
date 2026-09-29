import {
  X, Search, Users, Clock, CalendarDays, Phone, MessageSquare,
  ChevronRight, ChevronLeft, Check, Ban, AlertCircle, Armchair,
  Loader2, User, MapPin, Utensils, Timer, Coffee
} from "lucide-react";

export function StepIndicator({ current, steps }) {
  return (
    <div className="flex items-center gap-1 px-1">
      {steps.map((step, i) => (
        <div key={i} className="flex items-center gap-1">
          <div className={`
            flex items-center justify-center w-6 h-6 rounded-full text-[11px] font-semibold transition-all duration-300
            ${i < current ? "bg-emerald-500 text-white" :
              i === current ? "bg-amber-500 text-zinc-900 ring-2 ring-amber-500/30 ring-offset-1 ring-offset-zinc-900" :
              "bg-zinc-800 text-zinc-500"}
          `}>
            {i < current ? <Check size={12} /> : i + 1}
          </div>
          <span className={`text-[11px] hidden sm:inline ${
            i === current ? "text-zinc-200 font-medium" : "text-zinc-600"
          }`}>
            {step}
          </span>
          {i < steps.length - 1 && (
            <div className={`w-4 h-px mx-0.5 ${i < current ? "bg-emerald-500/50" : "bg-zinc-800"}`} />
          )}
        </div>
      ))}
    </div>
  );
}