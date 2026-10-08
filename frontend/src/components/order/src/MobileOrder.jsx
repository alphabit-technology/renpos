import { memo, useCallback, useState } from "react";
import { DeliveryBanner } from "@c/delivery/DeliveryBanner";
import { modifierTexts } from "../modifierRules";
import {
  X, ChevronLeft, ChevronRight, MoreHorizontal, Users2, ShoppingBag,
  Minus, Plus, Trash2, StickyNote, Send, CreditCard, Printer, Split,
  ArrowRightLeft, RefreshCw, Ban, UserRound, FileText, ChefHat, SlidersHorizontal, Flame,
} from "lucide-react";
import { flt, formatCurrency } from "../orderItems/calculator";
import { STATUS_CONFIG, DEFAULT_STATUS } from "../orderItems/OrderItemRow";
import { OrderTabs } from "./OrderTabs";
import { ItemCatalog } from "./ItemCatalog";

/**
 * MobileOrder — phone layout of the order manager.
 *
 *  ┌ header: close/back · table · customer · guests · ⋯
 *  ├ order chips (one row)
 *  ├ body: item catalog  |  order lines with inline editor
 *  └ footer: cart bar (catalog)  |  totals + Send / Pay (order)
 *
 * Tapping a catalog item adds it and stays in the catalog (the card shows
 * the ordered qty); the cart bar opens the order. Everything else lives in
 * the "⋯" action sheet.
 */

const SAFE_BOTTOM = { paddingBottom: "max(0.75rem, env(safe-area-inset-bottom))" };

// ─────────────────────────────────────────────
// Header
// ─────────────────────────────────────────────

const MobileHeader = memo(function MobileHeader({
  view, title, customer, dinners, onClose, onBack, onCustomer, onDinners, onMore, orderTabsProps,
}) {
  const iconBtn = "w-10 h-10 shrink-0 flex items-center justify-center rounded-xl text-muted-foreground hover:text-foreground hover:bg-muted/60 active:bg-muted transition-colors";

  return (
    <header className="shrink-0 border-b border-border bg-card">
      <div className="flex items-center gap-1 px-1.5 h-14">
        {view === "order" ? (
          <button className={iconBtn} onClick={onBack} aria-label={__("Back to items")}>
            <ChevronLeft size={22} />
          </button>
        ) : (
          <button className={iconBtn} onClick={onClose} aria-label={__("Close")}>
            <X size={20} />
          </button>
        )}

        <button onClick={onCustomer} className="flex-1 min-w-0 text-left px-1">
          <div className="text-[15px] font-semibold leading-tight truncate text-card-foreground">{title}</div>
          <div className="text-xs leading-tight truncate text-indigo-400 flex items-center gap-1">
            <UserRound size={11} className="shrink-0" />
            {customer || __("Guest")}
          </div>
        </button>

        <button onClick={onDinners} className="h-9 shrink-0 px-2.5 flex items-center gap-1.5 rounded-xl bg-muted/50 text-sm text-muted-foreground hover:text-foreground">
          <Users2 size={15} />
          <span className="tabular-nums">{dinners || 0}</span>
        </button>
        <button className={iconBtn} onClick={onMore} aria-label={__("More actions")}>
          <MoreHorizontal size={20} />
        </button>
      </div>

      <div className="flex items-stretch h-10 px-1.5 pb-1.5 gap-2">
        <span className="self-center pl-2 text-[11px] uppercase tracking-wide text-muted-foreground shrink-0">
          {__("Orders")}
        </span>
        <OrderTabs {...orderTabsProps} />
      </div>
    </header>
  );
});

// ─────────────────────────────────────────────
// Catalog footer: cart bar
// ─────────────────────────────────────────────

const CartBar = memo(function CartBar({ count, pending, total, onOpen }) {
  const empty = count === 0;
  return (
    <div className="shrink-0 px-3 pt-2 border-t border-border bg-card" style={SAFE_BOTTOM}>
      <button
        onClick={onOpen}
        className={`w-full h-14 rounded-2xl px-4 flex items-center gap-3 transition-all active:scale-[0.99] ${
          empty ? "bg-muted/60 text-muted-foreground" : "bg-blue-600 text-white shadow-lg shadow-blue-600/25"
        }`}
      >
        {/* remounts on every change so the badge pops */}
        <span key={`${count}-${total}`} className="relative animate-scale-in">
          <ShoppingBag size={22} />
          {!empty && (
            <span className="absolute -top-2 -right-2.5 min-w-[18px] h-[18px] px-1 rounded-full bg-white text-blue-700 text-[10px] font-bold flex items-center justify-center">
              {count}
            </span>
          )}
        </span>
        <span className="flex-1 text-left leading-tight ml-1">
          <span className="block text-sm font-semibold">{empty ? __("Order is empty") : __("View order")}</span>
          {pending > 0 && (
            <span className="block text-[11px] opacity-80">{__("{0} to send", [pending])}</span>
          )}
        </span>
        <span className="text-lg font-bold tabular-nums">{formatCurrency(total)}</span>
        <ChevronRight size={18} className="opacity-70 -mr-1" />
      </button>
    </div>
  );
});

// ─────────────────────────────────────────────
// Order lines
// ─────────────────────────────────────────────

function NumberField({ label, value, onCommit, disabled, suffix }) {
  // remounted (key) when the stored value changes, so the draft starts fresh
  const [draft, setDraft] = useState(String(flt(value)));

  const commit = () => {
    const v = flt(draft);
    if (v !== flt(value)) onCommit(v);
    else setDraft(String(flt(value)));
  };

  return (
    <label className={`flex-1 min-w-0 flex flex-col gap-0.5 ${disabled ? "opacity-40" : ""}`}>
      <span className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</span>
      <span className="relative">
        <input
          type="number"
          inputMode="decimal"
          disabled={disabled}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
          className="w-full h-10 rounded-xl bg-background border border-border px-3 text-sm tabular-nums outline-none focus:border-ring"
        />
        {suffix && <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">{suffix}</span>}
      </span>
    </label>
  );
}

const LineEditor = memo(function LineEditor({ item, canEdit, canDiscount, canRate, canDelete, canModify, onUpdate, onDelete, onNotes, onModifiers }) {
  const stepBtn = "w-11 h-11 rounded-xl border border-border bg-background flex items-center justify-center active:bg-muted disabled:opacity-30";

  return (
    <div className="px-3 pb-3 pt-1 space-y-3 animate-slide-up">
      {canEdit ? (
        <div className="flex items-center gap-2">
          <button className={stepBtn} onClick={() => onUpdate("qty", Math.max(0, flt(item.qty) - 1))}>
            <Minus size={18} />
          </button>
          <div className="w-12 text-center text-lg font-semibold tabular-nums">{flt(item.qty)}</div>
          <button className={stepBtn} onClick={() => onUpdate("qty", flt(item.qty) + 1)}>
            <Plus size={18} />
          </button>
          <div className="flex-1" />
          {canModify && (
            <button className={`${stepBtn} text-blue-400`} onClick={onModifiers} aria-label={__("Options")}>
              <SlidersHorizontal size={17} />
            </button>
          )}
          <button className={`${stepBtn} text-muted-foreground`} onClick={onNotes} aria-label={__("Notes")}>
            <StickyNote size={17} />
          </button>
          <button className={`${stepBtn} text-destructive border-destructive/30`} disabled={!canDelete} onClick={onDelete} aria-label={__("Remove")}>
            <Trash2 size={17} />
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <ChefHat size={14} />
          <span className="flex-1">{__("Already sent to the kitchen")}</span>
          {canDelete && (
            <button className={`${stepBtn} text-destructive border-destructive/30`} onClick={onDelete} aria-label={__("Remove")}>
              <Trash2 size={17} />
            </button>
          )}
        </div>
      )}

      {canEdit && (canDiscount || canRate) && (
        <div className="flex gap-2">
          {canDiscount && (
            <NumberField key={`d-${item.discount_percentage}`} label={__("Discount")} suffix="%" value={item.discount_percentage}
              onCommit={(v) => onUpdate("discount", v)} />
          )}
          {canRate && (
            <NumberField key={`r-${item.rate}`} label={__("Rate")} value={item.rate} onCommit={(v) => onUpdate("rate", v)} />
          )}
        </div>
      )}
    </div>
  );
});

const OrderLine = memo(function OrderLine({ item, expanded, onToggle, editorProps }) {
  const cfg = STATUS_CONFIG[item.status] || DEFAULT_STATUS;
  const Icon = cfg.icon;
  const discount = flt(item.discount_percentage);

  return (
    <div className={`border-b border-border ${expanded ? "bg-muted/30" : ""}`}>
      <button onClick={() => onToggle(item.identifier)} className="w-full flex items-center gap-3 px-3 py-3 text-left active:bg-muted/40">
        <span className={`w-9 h-9 shrink-0 rounded-xl flex items-center justify-center ${cfg.bg} ${cfg.text}`}>
          <Icon size={16} />
        </span>
        <span className="flex-1 min-w-0">
          <span className="block text-sm font-medium truncate text-card-foreground">
            <span className="tabular-nums text-muted-foreground mr-1.5">{flt(item.qty)}×</span>
            {item.item_name}
          </span>
          {modifierTexts(item.modifiers).length > 0 && (
            <span className="block text-xs text-blue-400/90 leading-snug">
              {modifierTexts(item.modifiers).join(" · ")}
            </span>
          )}
          <span className="block text-xs text-muted-foreground truncate">
            {__(item.status || "Pending")} · @{formatCurrency(item.rate)}
            {discount > 0 && <span className="text-emerald-400"> −{discount}%</span>}
            {item.notes && <span className="italic"> · {item.notes}</span>}
          </span>
        </span>
        <span className="text-sm font-semibold tabular-nums shrink-0">{formatCurrency(item.amount)}</span>
      </button>
      {expanded && <LineEditor item={item} {...editorProps} />}
    </div>
  );
});

// ─────────────────────────────────────────────
// Action sheet
// ─────────────────────────────────────────────

function ActionSheet({ open, onClose, actions }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[1040] flex flex-col justify-end bg-black/60 animate-fade-in" onClick={onClose}>
      <div className="rounded-t-3xl bg-card border-t border-border px-2 pt-2 animate-slide-up" style={SAFE_BOTTOM} onClick={(e) => e.stopPropagation()}>
        <div className="mx-auto mb-2 h-1 w-10 rounded-full bg-muted-foreground/30" />
        {actions.filter(Boolean).map(({ key, icon: Icon, label, onClick, disabled, danger }) => (
          <button
            key={key}
            disabled={disabled}
            onClick={() => { onClose(); onClick?.(); }}
            className={`w-full h-12 px-4 flex items-center gap-3 rounded-xl text-[15px] text-left active:bg-muted disabled:opacity-35 ${
              danger ? "text-destructive" : "text-card-foreground"
            }`}
          >
            <Icon size={19} className={danger ? "" : "text-muted-foreground"} />
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// Main
// ─────────────────────────────────────────────

export function MobileOrder({
  om, title, customer, orderTabsProps, pendingCls,
  onClose, onItemClick, onPay, onAccount, onDivide, onTransfer, onVoid, onRefresh,
  onCustomer, onDinners, onOrderNotes, hasModifiers, onEditModifiers, onDeleteItem,
}) {
  const [view, setView] = useState("items");
  const [expandedId, setExpandedId] = useState(null);
  const [moreOpen, setMoreOpen] = useState(false);

  const hasOrder = !!om.currentOrder;
  const hasItems = om.itemsList.length > 0;
  const count = om.itemsList.reduce((n, i) => n + flt(i.qty), 0);

  // the editor closes by itself when its line disappears (order switch, delete)
  const openId = expandedId && om.items[expandedId] ? expandedId : null;

  const toggleLine = useCallback((identifier) => {
    om.setCurrentItemId(identifier);
    setExpandedId((cur) => (cur === identifier ? null : identifier));
  }, [om]);

  const openNotes = useCallback((item) => {
    frappe.prompt(
      { fieldname: "notes", fieldtype: "Small Text", label: __("Notes"), default: item.notes || "" },
      ({ notes }) => om.updateItemNotes(item.identifier, notes || ""),
      __("Notes for {0}", [item.item_name]),
      __("Save"),
    );
  }, [om]);

  const actions = [
    { key: "customer", icon: UserRound, label: __("Customer"), onClick: onCustomer, disabled: !hasOrder },
    { key: "guests", icon: Users2, label: __("Guests"), onClick: onDinners, disabled: !hasOrder },
    { key: "notes", icon: FileText, label: __("Order notes"), onClick: onOrderNotes, disabled: !hasOrder },
    { key: "bill", icon: Printer, label: __("Print bill"), onClick: onAccount, disabled: !hasItems },
    { key: "divide", icon: Split, label: __("Divide order"), onClick: onDivide, disabled: !hasItems },
    { key: "transfer", icon: ArrowRightLeft, label: __("Transfer to another table"), onClick: onTransfer, disabled: !hasOrder },
    { key: "refresh", icon: RefreshCw, label: __("Refresh"), onClick: onRefresh },
    { key: "void", icon: Ban, label: __("Void order"), onClick: onVoid, disabled: !hasOrder, danger: true },
  ];

  return (
    <div className="flex flex-col h-full overflow-hidden bg-card text-card-foreground">
      <MobileHeader
        view={view}
        title={title}
        customer={customer}
        dinners={om.currentOrder?.dinners}
        onClose={onClose}
        onBack={() => setView("items")}
        onCustomer={onCustomer}
        onDinners={onDinners}
        onMore={() => setMoreOpen(true)}
        orderTabsProps={orderTabsProps}
      />

      {view === "items" ? (
        <>
          <div className="flex-1 min-h-0 flex flex-col">
            <ItemCatalog onItemClick={onItemClick} />
          </div>
          <CartBar
            count={count}
            pending={om.pendingCount}
            total={om.totals.grandTotal}
            onOpen={() => setView("order")}
          />
        </>
      ) : (
        <>
          <DeliveryBanner order={om.currentOrder} itemsTotal={om.totals.itemsTotal} compact />
          <div className={`flex-1 min-h-0 overflow-y-auto overscroll-contain ${pendingCls}`}>
            {hasItems ? (
              om.itemsList.map((item) => {
                const id = item.identifier;
                const canEdit = om.isItemEditable(id);
                return (
                  <OrderLine
                    key={id}
                    item={item}
                    expanded={openId === id}
                    onToggle={toggleLine}
                    editorProps={{
                      canEdit: !!canEdit,
                      canDiscount: !!canEdit,
                      canRate: !!canEdit,
                      canDelete: !!om.isItemDeletable(id),
                      canModify: !!(canEdit && hasModifiers?.(item.item_code)),
                      onModifiers: () => onEditModifiers?.(id),
                      onUpdate: (field, value) => om.updateItem(id, field, value),
                      onDelete: () => onDeleteItem(id),
                      onNotes: () => openNotes(item),
                    }}
                  />
                );
              })
            ) : (
              <div className="h-full flex flex-col items-center justify-center gap-2 text-muted-foreground">
                <ShoppingBag size={36} className="opacity-30" />
                <span className="text-sm">{hasOrder ? __("No items yet") : __("Select or create an order")}</span>
              </div>
            )}
            <button
              onClick={() => setView("items")}
              className="w-full flex items-center justify-center gap-2 py-4 text-sm font-medium text-blue-400 active:bg-muted/40"
            >
              <Plus size={16} /> {__("Add items")}
            </button>
          </div>

          <footer className="shrink-0 border-t border-border bg-card px-3 pt-3 space-y-3" style={SAFE_BOTTOM}>
            <div className="flex items-end justify-between">
              <span className="text-xs text-muted-foreground">
                {__("Tax")} {formatCurrency(om.totals.totalTax)}
              </span>
              <span className="text-2xl font-extrabold tabular-nums leading-none">
                {formatCurrency(om.totals.grandTotal)}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {om.pendingCount === 0 && om.heldCount > 0 ? (
                <button
                  onClick={() => om.sendOrder(true)}
                  disabled={!hasOrder}
                  className="h-13 min-h-[52px] rounded-2xl flex items-center justify-center gap-2 font-semibold bg-orange-600 text-white active:bg-orange-700"
                >
                  <Flame size={18} />
                  {__("Fire")}
                  <span className="min-w-[20px] h-5 px-1.5 rounded-full bg-white/25 text-xs flex items-center justify-center">{om.heldCount}</span>
                </button>
              ) : (
                <button
                  onClick={om.sendOrder}
                  disabled={!hasOrder || om.pendingCount === 0}
                  className="h-13 min-h-[52px] rounded-2xl flex items-center justify-center gap-2 font-semibold bg-emerald-600 text-white active:bg-emerald-700 disabled:bg-muted disabled:text-muted-foreground"
                >
                  <Send size={18} />
                  {__("Send")}
                  {om.pendingCount > 0 && (
                    <span className="min-w-[20px] h-5 px-1.5 rounded-full bg-white/25 text-xs flex items-center justify-center">{om.pendingCount}</span>
                  )}
                </button>
              )}
              <button
                onClick={onPay}
                disabled={!hasItems}
                className="min-h-[52px] rounded-2xl flex items-center justify-center gap-2 font-semibold bg-blue-600 text-white active:bg-blue-700 disabled:bg-muted disabled:text-muted-foreground"
              >
                <CreditCard size={18} />
                {__("Pay")}
              </button>
            </div>
          </footer>
        </>
      )}

      <ActionSheet open={moreOpen} onClose={() => setMoreOpen(false)} actions={actions} />
    </div>
  );
}

export default MobileOrder;
