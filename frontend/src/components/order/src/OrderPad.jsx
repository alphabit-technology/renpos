import { memo, useCallback } from "react";
import {
  Delete, Minus as MinusIcon, Plus as PlusIcon, Trash2,
  Send, CreditCard, FileText, Split, ArrowRightLeft,
  Users2Icon, Ticket, PencilIcon, StarsIcon, PrinterIcon, Trash2Icon
} from "lucide-react";
import { flt, formatCurrency } from "../orderItems/calculator";

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
// ═════════════════════════════════════════════════

function ActionButton({ icon: Icon, label, onClick, disabled, badge, variant }) {
  const base = "flex-1 flex flex-col items-center justify-center gap-1 text-[10px] font-semibold transition-all relative border border-border/60 rounded-lg";

  const variants = {
    send: [
      "bg-emerald-600 hover:bg-emerald-500 active:bg-emerald-700 border-emerald-500/50",
      disabled ? "disabled:bg-muted disabled:text-foreground/40 disabled:border-border/30" : "text-white",
    ].join(" "),
    default: [
      "bg-muted/30 text-muted-foreground hover:bg-muted hover:text-foreground hover:border-border active:bg-muted/80",
      "disabled:text-foreground/30 disabled:border-border/30"
    ].join(" "),
  };
  //ssh -N -L 0.0.0.0:80:192.168.2.3 ubuntu@192.168.2.3
//192.168.139.3
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`${base} ${variants[variant] || variants.default}`}
    >
      <Icon size={16} />
      <span>{label}</span>
      <Badge visible={badge > 0}>{badge}</Badge>
    </button>
  );
}

// ═════════════════════════════════════════════════
// SINGLE ACTION (Guests, Notes, Promo, Void)
// ═════════════════════════════════════════════════

function SingleAction({ action, className = "", Icon, label, badge, children }) {
  return (
    <button
      onClick={action}
      className={`relative flex-1 flex flex-col items-center justify-center gap-0.5
                  border border-border/60 rounded-lg bg-muted/30
                  text-muted-foreground hover:bg-muted hover:text-foreground hover:border-border
                  active:bg-muted/80 transition-all ${className}`}
    >
      {Icon && <Icon size={16} />}
      {label && <span className="text-[9px] font-medium leading-none">{label}</span>}
      {children}
      <Badge visible={badge != null}>{badge}</Badge>
    </button>
  );
}

// ═════════════════════════════════════════════════
// MAIN ORDER PAD
// ═════════════════════════════════════════════════

export const OrderPad = memo(function OrderPad({
  currentItem, numpadField, canEdit, canDiscount, canRate, canDelete,
  onFieldSelect, onMinus, onPlus, onDelete,
  activeField, value, onChange, onEnter,
  totalTax = 0, grandTotal = 0,
  onSendOrder, onPay, onAccount, onDivide, onTransfer, onVoid, onRefresh,
  pendingCount = 0, hasItems = false, hasOrder = false,
  currentOrder
}) {
  const actionDinners = () => {
    MetaForm.save("Table Order", currentOrder?.name, {
      title: __("Set dinners"),
      fields: ["dinners"],
      onSave: () => onRefresh?.(),
    });
  };

  const actionNotes = () => {
    MetaForm.save("Table Order", currentOrder?.name, {
      title: __("Set note"),
      fields: ["notes"],
      onSave: () => onRefresh?.(),
    });
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
        onFieldSelect={onFieldSelect}
        onMinus={onMinus}
        onPlus={onPlus}
        onDelete={onDelete}
      />

      <div className="flex">
        <div className="flex-1 p-2">
          <NumPadGrid
            activeField={activeField}
            value={value}
            onChange={onChange}
            onEnter={onEnter}
          />
        </div>

        <div className="w-48 grid grid-cols-[1fr_2fr] gap-1.5 p-2 border-l border-border">
          <div className="flex flex-col gap-1.5">
            <SingleAction
              action={actionDinners}
              Icon={Users2Icon}
              label={__("Guests")}
              badge={currentOrder?.dinners}
            />
            <SingleAction
              action={actionNotes}
              Icon={FileText}
              label={__("Notes")}
            />
            <SingleAction
              Icon={StarsIcon}
              label={__("Promo")}
            />
            <SingleAction
              action={onVoid}
              Icon={Trash2Icon}
              label={__("Void")}
              className="text-destructive/60 border-destructive/20 hover:text-destructive hover:bg-destructive/10 hover:border-destructive/30"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <ActionButton
              icon={Send}
              label={__("Send")}
              onClick={onSendOrder}
              disabled={pendingCount === 0 || !hasOrder}
              badge={pendingCount}
              variant="send"
            />
            <ActionButton
              icon={PrinterIcon}
              label={__("Bill")}
              onClick={onAccount}
              disabled={!hasItems}
            />
            <ActionButton
              icon={Split}
              label={__("Divide")}
              onClick={onDivide}
              disabled={!hasItems}
            />
            <ActionButton
              icon={ArrowRightLeft}
              label={__("Transfer")}
              onClick={onTransfer}
              disabled={!hasOrder}
            />
          </div>
        </div>
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
  onFieldSelect, onMinus, onPlus, onDelete,
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

        <button
          onClick={onDelete}
          disabled={!canDelete}
          className={`${controlBtn} hover:bg-destructive/10 hover:border-destructive/30`}
        >
          <Trash2 size={14} className="text-destructive" />
        </button>
      </div>
    </div>
  );
});

// ═════════════════════════════════════════════════
// NUMPAD GRID
// ═════════════════════════════════════════════════

const NumPadGrid = memo(function NumPadGrid({ activeField, value, onChange, onEnter }) {
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

  const keyCls = "h-11 rounded-lg bg-muted/30 border border-border hover:bg-muted active:bg-muted/80 text-foreground text-sm font-medium transition-all";

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