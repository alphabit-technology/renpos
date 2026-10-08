import { memo, useCallback } from "react";
import { usePersistedState } from "@/hooks/usePersistedState";
import {
  Delete, Minus as MinusIcon, Plus as PlusIcon, Trash2,
  Send, CreditCard, FileText, Split, ArrowRightLeft,
  Users2Icon, PrinterIcon, Trash2Icon, SlidersHorizontal, PauseCircle, Flame, Calculator
} from "lucide-react";
import { flt, formatCurrency } from "../orderItems/calculator";
import OrderAPI from "../api";

/**
 * OrderPad — Compact editing + actions panel (v3).
 *
 * v3 fix: disabled states use text-foreground/40 instead of
 * text-muted-foreground which was invisible in light theme.
 */

// ═════════════════════════════════════════════════
// SHARED BADGE
// ═════════════════════════════════════════════════

function Badge({ children, visible = true }) {
  if (!visible) return null;
  return (
    <span className="absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px] rounded-full text-[10px] font-bold flex items-center justify-center px-1 shadow-md bg-amber-500 text-black shadow-amber-500/30 z-10 ring-2 ring-background">
      {children}
    </span>
  );
}

// ═════════════════════════════════════════════════
// ACTION BUTTON (Send, Bill, Divide, Transfer)
// label on the left, icon on the right; Send is the big one
// ═════════════════════════════════════════════════

function ActionButton({ icon: Icon, label, hint, onClick, disabled, badge, variant, className = "" }) {
  const primary = variant === "send" || variant === "fire";
  const tone = primary
    ? (disabled
        ? "bg-muted/40 text-foreground/35 border-border/30"
        : variant === "fire"
          ? "bg-orange-600 hover:bg-orange-500 active:bg-orange-700 border-orange-500/50 text-white shadow-sm shadow-orange-900/30"
          : "bg-emerald-600 hover:bg-emerald-500 active:bg-emerald-700 border-emerald-500/50 text-white shadow-sm shadow-emerald-900/30")
    : "bg-muted/30 text-foreground/85 border-border/60 hover:bg-muted hover:text-foreground hover:border-border active:bg-muted/80 disabled:text-foreground/30 disabled:border-border/30 disabled:bg-muted/10";
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`relative w-full flex items-center justify-between gap-2 px-3 rounded-lg border text-left transition-all disabled:cursor-not-allowed ${tone} ${className}`}
    >
      <span className="min-w-0 flex flex-col">
        <span className={`${primary ? "text-[15px] font-bold" : "text-[13px] font-semibold"} leading-tight truncate`}>{label}</span>
        {hint && <span className={`text-[11px] leading-tight truncate ${primary && !disabled ? "text-white/80" : "text-muted-foreground"}`}>{hint}</span>}
      </span>
      <Icon size={primary ? 20 : 16} className={`shrink-0 ${primary ? "" : "opacity-70"}`} />
      <Badge visible={badge > 0}>{badge}</Badge>
    </button>
  );
}

// ═════════════════════════════════════════════════
// SINGLE ACTION (Guests, Notes, Hold, Void): one row under the pad
// ═════════════════════════════════════════════════

function SingleAction({ action, className = "", Icon, label, badge, disabled, title }) {
  return (
    <button
      onClick={action}
      disabled={disabled}
      title={title}
      className={`relative min-w-0 h-10 flex items-center justify-center gap-1.5 px-1
                  border border-border/60 rounded-lg bg-muted/30
                  text-muted-foreground hover:bg-muted hover:text-foreground hover:border-border
                  active:bg-muted/80 transition-all disabled:opacity-40 disabled:pointer-events-none ${className}`}
    >
      {Icon && <Icon size={15} className="shrink-0" />}
      {label && <span className="text-[11px] xl:text-xs font-medium truncate">{label}</span>}
      <Badge visible={badge != null}>{badge}</Badge>
    </button>
  );
}

// ═════════════════════════════════════════════════
// MAIN ORDER PAD
// ═════════════════════════════════════════════════

export const OrderPad = memo(function OrderPad({
  currentItem, numpadField, canEdit, canDiscount, canRate, canDelete,
  onFieldSelect, onMinus, onPlus, onDelete, canModify, onModifiers,
  activeField, value, onChange, onEnter,
  totalTax = 0, grandTotal = 0,
  onSendOrder, onPay, onAccount, onDivide, onTransfer, onVoid, onRefresh,
  pendingCount = 0, hasItems = false, hasOrder = false,
  currentOrder, heldCount = 0, onFire, canHold = false, currentHeld = false, onHold,
}) {
  // nothing left to send but held lines: the green button fires them
  const firing = pendingCount === 0 && heldCount > 0;
  // through the order API: waiters can't write orders directly
  const actionDinners = () => {
    if (!currentOrder?.name) return;
    frappe.prompt(
      { fieldname: "dinners", fieldtype: "Int", label: __("Guests"), default: currentOrder.dinners || 1 },
      ({ dinners }) => OrderAPI.setDinners(currentOrder.name, dinners).then(() => onRefresh?.()),
      __("Set guests"), __("Save"));
  };

  // the keypad shows when it's needed (Qty / Disc% / Rate tapped, or the keypad
  // button); hidden, the order lines get the room. Remembered per device.
  const [padOpen, setPadOpen] = usePersistedState("ren_order_pad_open", false);
  const selectField = (field) => {
    if (!padOpen) setPadOpen(true);
    onFieldSelect(field);
  };

  const sendButton = (className) => (
    <ActionButton
      icon={firing ? Flame : Send}
      label={firing ? __("Fire") : __("Send")}
      hint={firing
        ? __("{0} held", [heldCount])
        : pendingCount > 0 ? __("{0} new", [pendingCount]) : __("Nothing new")}
      onClick={firing ? onFire : onSendOrder}
      disabled={(pendingCount === 0 && heldCount === 0) || !hasOrder}
      variant={firing ? "fire" : "send"}
      className={className}
    />
  );

  const actionNotes = () => {
    if (!currentOrder?.name) return;
    frappe.prompt(
      { fieldname: "notes", fieldtype: "Small Text", label: __("Note"), default: currentOrder.notes || "" },
      ({ notes }) => OrderAPI.setNotes(currentOrder.name, notes).then(() => onRefresh?.()),
      __("Set note"), __("Save"));
  };

  return (
    <div className="shrink-0 flex flex-col border-t border-border">
      <EditorRow
        currentItem={currentItem}
        numpadField={numpadField}
        canEdit={canEdit}
        canDiscount={canDiscount}
        canRate={canRate}
        canDelete={canDelete}
        onFieldSelect={selectField}
        onMinus={onMinus}
        onPlus={onPlus}
        onDelete={onDelete}
        canModify={canModify}
        onModifiers={onModifiers}
        padOpen={padOpen}
        onTogglePad={() => setPadOpen(!padOpen)}
      />

      {padOpen ? (
        <div className="flex gap-2 px-2 pt-2">
          <div className="flex-1 min-w-0">
            <NumPadGrid
              activeField={activeField}
              value={value}
              onChange={onChange}
              onEnter={onEnter}
            />
          </div>

          <div className="w-[46%] max-w-56 flex flex-col gap-1.5">
            {sendButton("flex-[1.7]")}
            <ActionButton icon={PrinterIcon} label={__("Bill")} onClick={onAccount} disabled={!hasItems} className="flex-1" />
            <ActionButton icon={Split} label={__("Divide")} onClick={onDivide} disabled={!hasItems} className="flex-1" />
            <ActionButton icon={ArrowRightLeft} label={__("Transfer")} onClick={onTransfer} disabled={!hasOrder} className="flex-1" />
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-1.5 px-2 pt-2">
          {sendButton("col-span-3 h-14")}
          <ActionButton icon={PrinterIcon} label={__("Bill")} onClick={onAccount} disabled={!hasItems} className="h-11" />
          <ActionButton icon={Split} label={__("Divide")} onClick={onDivide} disabled={!hasItems} className="h-11" />
          <ActionButton icon={ArrowRightLeft} label={__("Transfer")} onClick={onTransfer} disabled={!hasOrder} className="h-11" />
        </div>
      )}

      <div className="grid grid-cols-4 gap-1.5 p-2">
        <SingleAction action={actionDinners} Icon={Users2Icon} label={__("Guests")} badge={currentOrder?.dinners || null} />
        <SingleAction action={actionNotes} Icon={FileText} label={__("Notes")} />
        <SingleAction
          action={onHold}
          disabled={!canHold}
          Icon={PauseCircle}
          label={currentHeld ? __("Unhold") : __("Hold")}
          badge={heldCount || null}
          className={currentHeld ? "text-amber-400 border-amber-500/40" : ""}
        />
        <SingleAction
          action={onVoid}
          Icon={Trash2Icon}
          label={__("Void")}
          className="text-destructive/70 border-destructive/20 hover:text-destructive hover:bg-destructive/10 hover:border-destructive/30"
        />
      </div>

      <PayButton
        totalTax={totalTax}
        grandTotal={grandTotal}
        onPay={onPay}
        hasItems={hasItems}
      />
    </div>
  );
});

// ═════════════════════════════════════════════════
// PAY BUTTON
// ═════════════════════════════════════════════════

const PayButton = memo(function PayButton({ totalTax, grandTotal, onPay, hasItems }) {
  return (
    <button
      onClick={onPay}
      disabled={!hasItems}
      className={`w-full flex items-center justify-between px-4 py-3 transition-colors
                 ${hasItems
                   ? "bg-blue-600 hover:bg-blue-500 active:bg-blue-700 text-white"
                   : "bg-muted text-muted-foreground/80 cursor-not-allowed"
                 }`}
    >
      <div className="text-left">
        <span className="text-xs opacity-80 block leading-none mb-0.5">
          {__("Tax")} {formatCurrency(totalTax)}
        </span>
        <span className="text-xl font-extrabold leading-tight">
          {formatCurrency(grandTotal)}
        </span>
      </div>
      <div className="flex items-center gap-2 text-sm font-bold">
        <CreditCard size={18} />
        {__("Pay")} →
      </div>
    </button>
  );
});

// ═════════════════════════════════════════════════
// EDITOR ROW
// ═════════════════════════════════════════════════

const EditorRow = memo(function EditorRow({
  currentItem, numpadField, canEdit, canDiscount, canRate, canDelete,
  onFieldSelect, onMinus, onPlus, onDelete, canModify, onModifiers, padOpen, onTogglePad,
}) {
  const fieldBtn = (field, label, getValue, disabled) => {
    const active = numpadField === field;
    return (
      <button
        onClick={() => onFieldSelect(field)}
        disabled={disabled}
        className={`flex-1 h-9 rounded-lg text-sm font-medium transition-all disabled:text-foreground/30 ${
          active
            ? "bg-amber-500/20 text-amber-400 ring-1 ring-amber-500/40"
            : "bg-background text-foreground hover:bg-muted"
        }`}
      >
        <div className="text-[9px] text-muted-foreground leading-none mb-0.5">{label}</div>
        {currentItem ? getValue() : "—"}
      </button>
    );
  };

  const controlBtn = [
    "w-9 h-9 rounded-lg bg-background border border-border",
    "hover:bg-muted active:bg-muted/80",
    "disabled:text-foreground/30 disabled:border-border/30",
    "flex items-center justify-center transition-all"
  ].join(" ");

  return (
    <div className="px-3 py-2.5 bg-card/50 border-b border-border">
      <div className="flex items-center gap-1.5">
        <button onClick={onMinus} disabled={!canEdit} className={controlBtn}>
          <MinusIcon size={14} />
        </button>

        {fieldBtn("qty", __("Qty"), () => currentItem?.qty ?? 0, !canEdit)}
        {fieldBtn("discount", __("Disc%"), () => flt(currentItem?.discount_percentage), !canDiscount)}
        {fieldBtn("rate", __("Rate"), () => flt(currentItem?.rate), !canRate)}

        <button onClick={onPlus} disabled={!canEdit} className={controlBtn}>
          <PlusIcon size={14} />
        </button>

        {canModify && (
          <button onClick={onModifiers} className={`${controlBtn} text-blue-400`} title={__("Options")}>
            <SlidersHorizontal size={14} />
          </button>
        )}

        <button
          onClick={onDelete}
          disabled={!canDelete}
          className={`${controlBtn} hover:bg-destructive/10 hover:border-destructive/30`}
        >
          <Trash2 size={14} className="text-destructive" />
        </button>

        {onTogglePad && (
          <button
            onClick={onTogglePad}
            title={padOpen ? __("Hide keypad") : __("Show keypad")}
            className={`${controlBtn} ${padOpen ? "text-amber-400 border-amber-500/50 bg-amber-500/10" : "text-muted-foreground"}`}
          >
            <Calculator size={14} />
          </button>
        )}
      </div>
    </div>
  );
});

// ═════════════════════════════════════════════════
// NUMPAD GRID
// ═════════════════════════════════════════════════

const NumPadGrid = memo(function NumPadGrid({ activeField, value, onChange }) {
  const write = useCallback((key) => {
    if (!activeField) return;
    const current = String(value || "");
    if (key === ".") {
      if (current.includes(".")) return;
      onChange(activeField, current + ".");
    } else {
      const newVal = current === "0" ? key : current + key;
      onChange(activeField, parseFloat(newVal) || 0);
    }
  }, [activeField, value, onChange]);

  const del = useCallback(() => {
    if (!activeField) return;
    const current = String(value || "");
    const newVal = current.slice(0, -1);
    onChange(activeField, parseFloat(newVal) || 0);
  }, [activeField, value, onChange]);

  const keyCls = "h-10 rounded-lg bg-muted/30 border border-border hover:bg-muted active:bg-muted/80 text-foreground text-sm font-medium transition-all";

  const keys = [
    ["7", "8", "9"],
    ["4", "5", "6"],
    ["1", "2", "3"],
  ];

  return (
    <div className="grid grid-cols-3 gap-1.5">
      {keys.flat().map((k) => (
        <button key={k} onClick={() => write(k)} className={keyCls}>
          {k}
        </button>
      ))}
      <button onClick={() => write("0")} className={keyCls}>0</button>
      <button onClick={() => write(".")} className={keyCls}>.</button>
      <button
        onClick={del}
        className={`${keyCls} text-muted-foreground`}
      >
        <Delete size={16} className="mx-auto" />
      </button>
    </div>
  );
});

export default OrderPad;