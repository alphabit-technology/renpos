import { useState, useCallback, useEffect, useMemo } from "react";
import { Loader2, BookOpen } from "lucide-react";
import { useRooms } from "@/context/RoomsContext.jsx";
import Modal from "@c/ui/Modal";

import { OrderItems } from "./orderItems/OrderItems";
import { ItemCatalog } from "./src/ItemCatalog";
import { OrderTabs } from "./src/OrderTabs";
import { DeliveryBanner } from "@c/delivery/DeliveryBanner";
import { OrderPad } from "./src/OrderPad";
import { PaymentPanel } from "./src/PaymentPanel";
import { DivideDialog } from "./src/DivideDialog";
import { TransferDialog } from "./src/TransferDialog";
import { MobileOrder } from "./src/MobileOrder";
import { ModifierDialog } from "./src/ModifierDialog";
import { VoidDialog } from "./src/VoidDialog";

import usePosData from "./usePosData";
import OrderAPI from "./api";
import useOrderManager from "./useOrderManager";
import { QtyStoreProvider, useQtyStore } from "./OrderQtyStore";
import { useIsMobile } from "./hooks/useIsMobile";
import { useStableCallback } from "./hooks/useStableCallback";
import { flt } from "./orderItems/calculator";

// ═════════════════════════════════════════════════
// MAIN ORDER COMPONENT
// ═════════════════════════════════════════════════

// Which menu this table sells from: the room's own menu, or the restaurant's.
function MenuChip() {
  const { activeMenuInfo } = useRooms();
  const own = activeMenuInfo?.source === "room";
  return (
    <div
      className="flex items-center gap-1.5 px-3 text-sm text-muted-foreground shrink-0"
      title={own ? __("This room has its own menu") : __("Restaurant menu")}
    >
      <BookOpen size={15} className={own ? "text-amber-400" : ""} />
      <span className={own ? "text-amber-300 font-medium" : ""}>
        {activeMenuInfo ? activeMenuInfo.menu_name : __("No menu")}
      </span>
    </div>
  );
}

function Order({ table, tableName, posProfile, open, onClose, title }) {
  const isMobile = useIsMobile();
  const { posData, loading: posLoading, getItem } = usePosData(posProfile);
  const om = useOrderManager({ tableName, posData, onClose });

  const [payingOrder, setPayingOrder] = useState(null);
  const [dialog, setDialog] = useState(null); // "divide" | "transfer" | null
  // { item, groups, identifier? } — choosing the options of a new or existing line
  const [modifierTarget, setModifierTarget] = useState(null);
  // { kind: "item", identifier, title } | { kind: "order", title } — void with a reason
  const [voidTarget, setVoidTarget] = useState(null);

  const qtyStore = useQtyStore();
  useEffect(() => {
    qtyStore.setAll(om.itemsList);
  }, [om.itemsList, qtyStore]);

  const [numpadField, setNumpadField] = useState("qty");

  const numpadValue = useMemo(() => {
    if (!om.currentItem) return 0;
    switch (numpadField) {
      case "qty":      return om.currentItem.qty;
      case "discount": return om.currentItem.discount_percentage;
      case "rate":     return om.currentItem.rate;
      default:         return 0;
    }
  }, [om.currentItem, numpadField]);

  // ═══════════════════════════════════════════════
  // STABLE CALLBACKS
  // ═══════════════════════════════════════════════

  const modifierGroupsOf = (itemCode) => {
    const names = posData?.itemsByCode?.[itemCode]?.modifier_groups || [];
    return names.map((n) => posData?.modifierGroups?.[n]).filter((g) => g?.options?.length);
  };

  // a size (variant) of an item: what the dialog needs to switch to it
  const resolveVariant = useStableCallback((code) => {
    const item = getItem(code);
    if (!item) return null;
    return { item, groups: modifierGroupsOf(code), fromComponents: !!item.price_from_components };
  });

  const handleItemClick = useStableCallback((menuItem) => {
    const fullItem = getItem(menuItem.item_code) || menuItem;
    // sizes: the waiter picks one in the dialog; the line is that variant
    if (fullItem.variants?.variants?.length) {
      setModifierTarget({ item: fullItem, groups: [], variants: fullItem.variants });
      return;
    }
    const groups = modifierGroupsOf(fullItem.item_code);
    if (groups.length) {
      setModifierTarget({ item: fullItem, groups, fromComponents: !!fullItem.price_from_components });
      return;
    }
    om.pushItem(fullItem);
    // on phones the waiter keeps picking items; the cart bar shows the count
    if (isMobile) navigator.vibrate?.(10);
  });

  // options of a line already in the order (not sent yet)
  const handleEditModifiers = useStableCallback((identifier) => {
    const line = om.items[identifier];
    if (!line) return;
    const groups = modifierGroupsOf(line.item_code);
    if (!groups.length) return;
    setModifierTarget({
      identifier,
      groups,
      fromComponents: !!posData?.itemsByCode?.[line.item_code]?.price_from_components,
      initial: line.modifiers || [],
      item: { item_name: line.item_name, price_list_rate: flt(line.price_list_rate) - flt(line.modifiers_amount) },
    });
  });

  const handleModifiersConfirm = useStableCallback(({ modifiers, qty, item }) => {
    const target = modifierTarget;
    setModifierTarget(null);
    if (!target) return;
    if (target.identifier) {
      om.setItemModifiers(target.identifier, modifiers);
    } else {
      const chosen = item || target.item;  // the size chosen, for items with sizes
      const fromComponents = item ? !!item.price_from_components : target.fromComponents;
      // built from components: the options are the whole price
      const base = fromComponents ? { price_list_rate: 0, rate: 0 } : {};
      om.pushItem({ ...chosen, ...base, modifiers, qty });
      if (isMobile) navigator.vibrate?.(10);
    }
  });

  const handleSelectOrder = useStableCallback((orderName) => {
    om.selectOrder(orderName);
  });

  const handleAddOrder = useStableCallback(() => om.addOrder());

  const handleItemSelect = useStableCallback((identifier) => {
    om.setCurrentItemId(identifier);
  });

  const handleFieldSelect = useStableCallback((field) => {
    setNumpadField(field);
  });

  const handleMinus = useStableCallback(() => {
    if (!om.currentItem) return;
    const current = numpadField === "qty" ? om.currentItem.qty
      : numpadField === "discount" ? om.currentItem.discount_percentage
      : om.currentItem.rate;
    om.updateItem(om.currentItemId, numpadField, Math.max(0, flt(current) - 1));
  });

  const handlePlus = useStableCallback(() => {
    if (!om.currentItem) return;
    const current = numpadField === "qty" ? om.currentItem.qty
      : numpadField === "discount" ? om.currentItem.discount_percentage
      : om.currentItem.rate;
    om.updateItem(om.currentItemId, numpadField, flt(current) + 1);
  });

  // Pending lines go away directly; lines already sent need a void reason.
  const requestDeleteItem = useStableCallback((identifier) => {
    const line = om.items[identifier];
    if (!line) return;
    if (om.isItemEditable(identifier)) {
      om.deleteItem(identifier);
      return;
    }
    setVoidTarget({
      kind: "item",
      identifier,
      title: __("Void {0}× {1}", [flt(line.qty), line.item_name]),
    });
  });

  const handleDeleteItem = useStableCallback(() => {
    if (om.currentItemId) requestDeleteItem(om.currentItemId);
  });

  const handleVoidConfirm = useStableCallback((voidInfo) => {
    const target = voidTarget;
    setVoidTarget(null);
    if (!target) return;
    if (target.kind === "item") om.deleteItem(target.identifier, voidInfo);
    else om.deleteOrder(voidInfo);
  });

  const handleNumpadChange = useStableCallback((field, value) => {
    if (!om.currentItemId) return;
    om.updateItem(om.currentItemId, field, value);
  });

  const handleNumpadEnter = useCallback(() => {}, []);

  // ── Order management actions ──
  const handleDeleteOrder = useStableCallback(() => {
    if (!om.currentOrderName) return;
    if (om.itemsList.some((i) => !om.isItemEditable(i.identifier))) {
      setVoidTarget({ kind: "order", title: __("Void order {0}", [om.currentOrder?.short_name || om.currentOrderName]) });
      return;
    }
    frappe.confirm(
      __("Void order {0}?", [om.currentOrder?.short_name || om.currentOrderName]),
      () => om.deleteOrder()
    );
  });

  // Print the pre-bill (Order Account print format) for the customer
  const handleAccount = useStableCallback(async () => {
    if (!om.currentOrderName) return;
    await om.waitForSync();
    if (posData?.receiptPrinter) {
      OrderAPI.printBill(om.currentOrderName).then(
        () => frappe.show_alert({ message: __("Bill sent to {0}", [posData.receiptPrinter]), indicator: "green" }),
        () => {}
      );
      return;
    }
    const params = new URLSearchParams({
      doctype: "Ren Order",
      name: om.currentOrderName,
      format: "Order Account",
      trigger_print: 1,
      no_letterhead: 0,
    });
    window.open(`/printview?${params}`, "_blank");
  });

  const handleRefresh = useStableCallback(() => {
    om.loadOrders({ preserveSelection: true, silent: true });
  });

  // ── Payment ──
  const handlePay = useStableCallback(() => {
    if (om.currentOrderName && om.itemsList.length) setPayingOrder(om.currentOrderName);
  });

  const handlePaid = useStableCallback(() => {
    // The invoiced order leaves the table's open orders
    om.loadOrders({ preserveSelection: false, silent: false });
  });

  // ─── Loading ───
  if (posLoading || om.loading) {
    return (
      <div className="flex items-center justify-center h-full bg-background">
        <Loader2 size={32} className="animate-spin text-muted-foreground" />
      </div>
    );
  }

  // ─── Permissions ───
  const canEdit     = om.currentItem && om.isItemEditable(om.currentItemId);
  const canDelete   = om.currentItem && om.isItemDeletable(om.currentItemId);
  // anyone can try: beyond their role, a manager PIN approves (utils/approval.js)
  const canDiscount = canEdit;
  const canRate     = canEdit;

  const pendingCls = om.isItemsPending
    ? "opacity-60 transition-opacity duration-150"
    : "transition-opacity duration-150";

  // ── Shared OrderPad props ──
  const orderPadProps = {
    // Editor
    currentOrder: om.currentOrder,
    currentItem: om.currentItem,
    numpadField,
    canEdit: !!canEdit,
    canDiscount: !!canDiscount,
    canRate: !!canRate,
    canDelete: !!canDelete,
    onFieldSelect: handleFieldSelect,
    onMinus: handleMinus,
    onPlus: handlePlus,
    onDelete: handleDeleteItem,
    canModify: !!(canEdit && om.currentItem && modifierGroupsOf(om.currentItem.item_code).length),
    onModifiers: () => om.currentItemId && handleEditModifiers(om.currentItemId),
    // NumPad
    activeField: numpadField,
    value: numpadValue,
    onChange: handleNumpadChange,
    onEnter: handleNumpadEnter,
    // Totals
    totalTax: om.totals.totalTax,
    grandTotal: om.totals.grandTotal,
    // Actions
    onSendOrder: om.sendOrder,
    onFire: () => om.sendOrder(true),
    heldCount: om.heldCount,
    // hold the selected line for a later course (lines not sent yet)
    canHold: !!(canEdit && om.currentItem),
    currentHeld: !!om.currentItem?.ren_hold,
    onHold: () => om.currentItemId && om.toggleHold(om.currentItemId),
    onPay: handlePay,
    onAccount: handleAccount,
    onDivide: () => setDialog("divide"),
    onTransfer: () => setDialog("transfer"),
    onVoid: handleDeleteOrder,
    onRefresh: handleRefresh,
    pendingCount: om.pendingCount,
    hasItems: om.itemsList.length > 0,
    hasOrder: !!om.currentOrder,
  };

  // ── Shared OrderTabs props ──
  const orderTabsProps = {
    orders: om.orders,
    currentOrderName: om.currentOrderName,
    onSelectOrder: handleSelectOrder,
    onAddOrder: handleAddOrder,
    onDeleteOrder: handleDeleteOrder,
  };

  // ═══════════════════════════════════════════════
  // MOBILE LAYOUT
  // ═══════════════════════════════════════════════

  // Customer, guests and note go through the order API (waiters can't write orders directly)
  const actionCustomer = () => {
    if (!om?.currentOrder?.name) return;
    frappe.prompt(
      { fieldname: "customer", fieldtype: "Link", options: "Customer", label: __("Customer"), reqd: 1,
        default: om.currentOrder.customer },
      ({ customer }) => OrderAPI.setCustomer(om.currentOrder.name, customer).then(() => handleRefresh()),
      __("Update Customer"), __("Save"));
  }

  const actionDinners = () => {
    if (!om?.currentOrder?.name) return;
    frappe.prompt(
      { fieldname: "dinners", fieldtype: "Int", label: __("Guests"), default: om.currentOrder.dinners || 1 },
      ({ dinners }) => OrderAPI.setDinners(om.currentOrder.name, dinners).then(() => handleRefresh()),
      __("Set guests"), __("Save"));
  };

  const actionOrderNotes = () => {
    if (!om?.currentOrder?.name) return;
    frappe.prompt(
      { fieldname: "notes", fieldtype: "Small Text", label: __("Note"), default: om.currentOrder.notes || "" },
      ({ notes }) => OrderAPI.setNotes(om.currentOrder.name, notes).then(() => handleRefresh()),
      __("Set note"), __("Save"));
  };

  const customerName = om.currentOrder?.customer_name || om.currentOrder?.customer || table.customer;

  const Mobile = (
    <MobileOrder
      om={om}
      posData={posData}
      title={title}
      customer={customerName}
      orderTabsProps={orderTabsProps}
      pendingCls={pendingCls}
      onClose={onClose}
      onItemClick={handleItemClick}
      onPay={handlePay}
      onAccount={handleAccount}
      onDivide={() => setDialog("divide")}
      onTransfer={() => setDialog("transfer")}
      onVoid={handleDeleteOrder}
      onRefresh={handleRefresh}
      onCustomer={actionCustomer}
      onDinners={actionDinners}
      onOrderNotes={actionOrderNotes}
      hasModifiers={(code) => modifierGroupsOf(code).length > 0}
      onEditModifiers={handleEditModifiers}
      onDeleteItem={requestDeleteItem}
    />
  );

  const Desk = (
    <div className="flex flex-col h-full overflow-hidden bg-card text-card-foreground">

      {/* ── Order Tabs (full width) ── */}
      

      {/* ── 2-panel body ── */}
      <div className="flex flex-1 min-h-0">
        <main className="flex-1 flex flex-col min-w-0 border-r border-border">
          <ItemCatalog onItemClick={handleItemClick} />
        </main>

        <aside className="w-[380px] xl:w-[440px] 2xl:w-[480px] shrink-0 flex flex-col">
          <button 
            onClick={actionCustomer} 
            className="shrink-0 flex items-center gap-1.5 px-3.5 py-1.5 text-md font-semibold whitespace-nowrap transition-all bg-indigo-500/15 text-indigo-400 border-b border-indigo-500/60"
          >
            <span className="link">
              {customerName || __('Guest')}
            </span>
          </button>
          <DeliveryBanner order={om.currentOrder} itemsTotal={om.totals.itemsTotal} />
          <div className={`flex-1 overflow-y-auto ${pendingCls}`}>  
            <OrderItems
              itemsList={om.itemsList}
              currentItemId={om.currentItemId}
              hasOrder={!!om.currentOrder}
              onItemSelect={handleItemSelect}
              isPending={om.isItemsPending}
            />
          </div>

          <OrderPad {...orderPadProps} />
        </aside>
      </div>
    </div>
  );

  return (
    <Modal size="full" compactHeader={true} hasReturn={false} showClose={!isMobile} title={isMobile ? null : (
      <div className="flex flex-row">
        <div className="group !bg-primary/40 relative flex items-center gap-1.5 px-3 py-1.5 text-lg font-medium transition-all min-w-0  shrink-0 bg-transparent text-foreground hover:bg-muted/50">
          <span>{title}</span>
        </div>
        <MenuChip />
        <OrderTabs {...orderTabsProps} />
      </div>
    )} onClose={onClose} open={open}>
      {isMobile ? Mobile: Desk}
      {payingOrder && <PaymentPanel
        key={payingOrder}
        open={!!payingOrder}
        orderName={payingOrder}
        title={title}
        waitForSync={om.waitForSync}
        onClose={() => setPayingOrder(null)}
        onPaid={handlePaid}
      />}
      {modifierTarget && <ModifierDialog
        key={modifierTarget.identifier || modifierTarget.item.item_code}
        item={modifierTarget.item}
        groups={modifierTarget.groups}
        fromComponents={!!modifierTarget.fromComponents}
        allGroups={posData?.modifierGroups || {}}
        modes={posData?.modifierModes || []}
        initial={modifierTarget.identifier ? modifierTarget.initial : undefined}
        variants={modifierTarget.variants || null}
        resolveVariant={resolveVariant}
        showQty={!modifierTarget.identifier}
        onConfirm={handleModifiersConfirm}
        onClose={() => setModifierTarget(null)}
      />}
      {voidTarget && <VoidDialog
        title={voidTarget.title}
        onConfirm={handleVoidConfirm}
        onClose={() => setVoidTarget(null)}
      />}
      {dialog === "divide" && <DivideDialog
        open
        items={om.itemsList}
        onClose={() => setDialog(null)}
        onConfirm={om.divideOrder}
      />}
      {dialog === "transfer" && <TransferDialog
        open
        orderName={om.currentOrderName}
        onClose={() => setDialog(null)}
        onConfirm={om.transferOrder}
      />}
    </Modal>
  )
}

export function OrderManager({ open, onClose, table, posProfile, ...props }) {
  if (!open) return null;

  const title = table
    ? `${table.room?.description || ""} (${table.description || ""})`
    : __("Order Manager");

  return (
      <QtyStoreProvider>
        <Order
          table={table}
          tableName={table?.name}
          posProfile={posProfile}
          onClose={onClose}
          open={open}
          title={title}
          {...props}
        />
      </QtyStoreProvider>
  );
}