import { memo } from "react";
import {
  Send, FileText, Split, ArrowRightLeft, CreditCard,
} from "lucide-react";

export const ActionButtons = memo(function ActionButtons({
  onSendOrder, pendingCount, hasItems, hasOrder, vertical = true,
}) {
  const layout = vertical
    ? "flex flex-col h-full"
    : "grid grid-cols-5 gap-1";

  const baseClass = 'flex items-center justify-between px-2 gap-1.5 font-medium border border-orange-500';
  return (
    <div className={layout}>
      <button
        onClick={onSendOrder}
        disabled={pendingCount === 0 || !hasOrder}
        className={`${baseClass} bg-emerald-600 hover:bg-emerald-500 disabled:bg-muted disabled:text-muted-foreground text-white transition-colors relative ${
          vertical
            ? "flex-1 flex-row text-xs"
            : "h-12 rounded-lg text-sm px-3"
        }`}
      >
        <span>Order</span>
        <Send size={16} />
        {pendingCount > 0 && (
          <span
            className={`min-w-[18px] h-[18px] rounded-bl-full bg-red-500 text-white text-[10px] font-bold px-2 absolute top-0 right-0`}
          >
            {pendingCount}
          </span>
        )}
      </button>

      <button
        disabled={!hasItems}
        className={`${baseClass} text-muted-foreground hover:bg-accent disabled:opacity-30 transition-colors ${
          vertical ? "flex-1 flex-row text-xs" : "h-12 rounded-lg bg-secondary text-xs"
        }`}
      >
        <span>Account</span>
        <FileText size={16} />
      </button>

      <button
        disabled={!hasItems}
        className={`${baseClass} text-muted-foreground hover:bg-accent disabled:opacity-30 transition-colors ${
          vertical ? "flex-1 flex-row text-xs" : "h-12 rounded-lg bg-secondary text-xs"
        }`}
      >
        <span>Divide</span>
        <Split size={16} />
      </button>

      <button
        disabled={!hasOrder}
        className={`${baseClass} text-muted-foreground hover:bg-accent disabled:opacity-30 transition-colors ${
          vertical ? "flex-1 flex-row text-xs" : "h-12 rounded-lg bg-secondary text-xs"
        }`}
      >
        <span>Transfer</span>
        <ArrowRightLeft size={16} />
      </button>

      <button
        disabled={!hasItems}
        className={`${baseClass} font-bold bg-blue-600 hover:bg-blue-500 disabled:bg-muted disabled:text-muted-foreground text-white transition-colors ${
          vertical ? "flex-1 flex-row text-xs" : "h-12 rounded-lg text-sm"
        }`}
      >
        <span>Complete</span>
        <CreditCard size={16} />
      </button>
    </div>
  );
});