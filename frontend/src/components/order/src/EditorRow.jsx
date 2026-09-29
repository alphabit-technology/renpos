import { memo } from "react";
import { Trash2, Minus as MinusIcon, Plus as PlusIcon } from "lucide-react";
import { flt } from "../orderItems/calculator";

export const EditorRow = memo(function EditorRow({
  currentItem, numpadField, canEdit, canDiscount, canRate, canDelete,
  onFieldSelect, onMinus, onPlus, onDelete,
}) {
  const inactiveCls = "bg-background border border-border text-foreground hover:bg-muted";

  return (
    <div className="border-t border-border px-3 py-2">
      <div className="flex items-center gap-1.5">
        <button
          onClick={onMinus}
          disabled={!canEdit}
          className={`w-9 h-9 rounded-lg ${inactiveCls} disabled:opacity-30 flex items-center justify-center transition-colors`}
        >
          <MinusIcon size={14} className="text-muted-foreground" />
        </button>

        <button
          onClick={() => onFieldSelect("qty")}
          disabled={!canEdit}
          className={`flex-1 h-9 rounded-lg text-sm font-medium transition-all disabled:opacity-30 ${
            numpadField === "qty"
              ? "bg-amber-500/20 text-amber-500 border border-amber-500/40"
              : inactiveCls
          }`}
        >
          <div className="text-[9px] text-muted-foreground leading-none mb-0.5">Qty</div>
          {currentItem?.qty ?? "—"}
        </button>

        <button
          onClick={() => onFieldSelect("discount")}
          disabled={!canDiscount}
          className={`flex-1 h-9 rounded-lg text-sm font-medium transition-all disabled:opacity-30 ${
            numpadField === "discount"
              ? "bg-amber-500/20 text-amber-500 border border-amber-500/40"
              : inactiveCls
          }`}
        >
          <div className="text-[9px] text-muted-foreground leading-none mb-0.5">Disc%</div>
          {currentItem ? flt(currentItem.discount_percentage) : "—"}
        </button>

        <button
          onClick={() => onFieldSelect("rate")}
          disabled={!canRate}
          className={`flex-1 h-9 rounded-lg text-sm font-medium transition-all disabled:opacity-30 ${
            numpadField === "rate"
              ? "bg-amber-500/20 text-amber-500 border border-amber-500/40"
              : inactiveCls
          }`}
        >
          <div className="text-[9px] text-muted-foreground leading-none mb-0.5">Rate</div>
          {currentItem ? flt(currentItem.rate) : "—"}
        </button>

        <button
          onClick={onPlus}
          disabled={!canEdit}
          className={`w-9 h-9 rounded-lg ${inactiveCls} disabled:opacity-30 flex items-center justify-center transition-colors`}
        >
          <PlusIcon size={14} className="text-muted-foreground" />
        </button>

        <button
          onClick={onDelete}
          disabled={!canDelete}
          className="w-9 h-9 rounded-lg bg-background border border-border hover:bg-rose-500/15 disabled:opacity-30 flex items-center justify-center transition-colors"
        >
          <Trash2 size={14} className="text-rose-400" />
        </button>
      </div>
    </div>
  );
}, (prev, next) => {
  return (
    prev.currentItem === next.currentItem &&
    prev.numpadField === next.numpadField &&
    prev.canEdit === next.canEdit &&
    prev.canDiscount === next.canDiscount &&
    prev.canRate === next.canRate &&
    prev.canDelete === next.canDelete &&
    prev.onFieldSelect === next.onFieldSelect &&
    prev.onMinus === next.onMinus &&
    prev.onPlus === next.onPlus &&
    prev.onDelete === next.onDelete
  );
});