import { memo, useCallback } from "react";
import { modifierTexts } from "../modifierRules";
import {
  ShoppingCart, Send, Flame, CheckCircle, Check, Circle, PauseCircle,
} from "lucide-react";
import { flt, formatCurrency } from "./calculator";

export const STATUS_CONFIG = {
  Pending:    { icon: ShoppingCart, text: "text-amber-400",   bg: "bg-amber-500/10",  border: "border-amber-500/20" },
  Attending:  { icon: ShoppingCart, text: "text-amber-400",   bg: "bg-amber-500/10",  border: "border-amber-500/20" },
  Sent:       { icon: Send,        text: "text-blue-400",    bg: "bg-blue-500/10",   border: "border-blue-500/20" },
  Processing: { icon: Flame,       text: "text-purple-400",  bg: "bg-purple-500/10", border: "border-purple-500/20" },
  Ready:      { icon: CheckCircle, text: "text-emerald-400", bg: "bg-emerald-500/10",border: "border-emerald-500/20" },
  Completed:  { icon: Check,       text: "text-muted-foreground", bg: "bg-muted/50",   border: "border-border" },
};

export const DEFAULT_STATUS = { icon: Circle, text: "text-muted-foreground", bg: "bg-muted/50", border: "border-border" };
// a line held for a later course (not sent yet)
export const HELD_STATUS = { icon: PauseCircle, text: "text-orange-400", bg: "bg-orange-500/10", border: "border-orange-500/20" };

export const OrderItemRow = memo(function OrderItemRow({
  item,
  selected,
  onClick,
}) {
  const config = item.ren_hold ? HELD_STATUS : (STATUS_CONFIG[item.status] || DEFAULT_STATUS);
  const StatusIcon = config.icon;
  const discount = flt(item.discount_percentage);

  const handleClick = useCallback(
    () => onClick(item.identifier),
    [onClick, item.identifier]
  );

  return (
    <div
      onClick={handleClick}
      className={`w-full text-left flex items-stretch border-b border-border transition-colors cursor-pointer ${
        selected
          ? "bg-amber-500/10"
          : "hover:bg-accent/50"
      }`}
    >
      {/* ── Full-height status icon ── */}
      <div
        className={`w-14 shrink-0 flex items-center justify-center ${config.bg} border-r ${config.border}`}
      >
        <StatusIcon size={20} className={config.text} />
      </div>

      {/* ── Content ── */}
      <div className="flex-1 flex items-center justify-between gap-2 px-3 py-2.5 min-w-0">
        <div className="min-w-0">
          <div className="text-sm font-medium text-card-foreground truncate">
            {item.item_name}
            {!!item.ren_hold && (
              <span className="ml-2 text-[10px] font-bold uppercase tracking-wide text-orange-400">{__("Held")}</span>
            )}
          </div>
          <div className="text-xs text-muted-foreground mt-0.5">
            {item.qty} x @{formatCurrency(item.rate)}
            {discount > 0 && (
              <span className="ml-1.5 text-emerald-400">
                -{flt(discount)}%
              </span>
            )}
          </div>
          {modifierTexts(item.modifiers).length > 0 && (
            <div className="text-[11px] text-blue-400/90 mt-0.5 leading-snug">
              {modifierTexts(item.modifiers).join(" · ")}
            </div>
          )}
          {item.notes && (
            <div className="text-[11px] text-muted-foreground/60 mt-0.5 truncate italic">
              {item.notes}
            </div>
          )}
        </div>

        <span className="text-sm font-semibold text-card-foreground shrink-0 tabular-nums">
          {formatCurrency(item.amount)}
        </span>
      </div>

      {/* ── Selected indicator ── */}
      {selected && (
        <div className="w-0.5 shrink-0 bg-amber-500" />
      )}
    </div>
  );
}, (prev, next) => {
  if (prev.selected !== next.selected) return false;
  if (prev.onClick !== next.onClick) return false;
  const a = prev.item;
  const b = next.item;
  return (
    a.identifier === b.identifier &&
    a.item_name === b.item_name &&
    a.qty === b.qty &&
    a.rate === b.rate &&
    a.amount === b.amount &&
    a.discount_percentage === b.discount_percentage &&
    a.status === b.status &&
    a.ren_hold === b.ren_hold &&
    a.notes === b.notes &&
    a.modifiers === b.modifiers
  );
});