import { useState, useCallback, useEffect, useMemo } from "react";
import { Loader2 } from "lucide-react";
import Modal from "@c/ui/Modal";

import { OrderItems } from "./orderItems/OrderItems";
import { ItemCatalog } from "./src/ItemCatalog";
import { OrderTabs } from "./src/OrderTabs";
import { OrderPad } from "./src/OrderPad";
import { PaymentPanel } from "./src/PaymentPanel";
import { DivideDialog } from "./src/DivideDialog";
import { TransferDialog } from "./src/TransferDialog";
import { MobileBottomTabs } from "./src/MobileBottomTabs";

import usePosData from "./usePosData";
import useOrderManager from "./useOrderManager";
import { QtyStoreProvider, useQtyStore } from "./OrderQtyStore";
import { useIsMobile, MOBILE_BREAKPOINT } from "./hooks/useIsMobile";
import { useStableCallback } from "./hooks/useStableCallback";
import { flt } from "./orderItems/calculator";
import { can, canOpenOrderManage } from '@/router/permissions';

// ═════════════════════════════════════════════════
// MAIN ORDER COMPONENT
// ═════════════════════════════════════════════════

function Order({ table, tableName, posProfile, open, onClose, title }) {
  const isMobile = useIsMobile();
  const { posData, loading: posLoading, getItem } = usePosData(posProfile);
  const om = useOrderManager({ tableName, posData, onClose });

  const [mobileTab, setMobileTab] = useState("items");
  const [payingOrder, setPayingOrder] = useState(null);
  const [dialog, setDialog] = useState(null); // "divide" | "transfer" | null

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

  const handleItemClick = useStableCallback((menuItem) => {
    const fullItem = getItem(menuItem.item_code) || menuItem;
    om.pushItem(fullItem);
    if (window.innerWidth < MOBILE_BREAKPOINT) {
      setMobileTab("cart");
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

  const handleDeleteItem = useStableCallback(() => {
    if (om.currentItemId) om.deleteItem(om.currentItemId);
  });

  const handleNumpadChange = useStableCallback((field, value) => {
    if (!om.currentItemId) return;
    om.updateItem(om.currentItemId, field, value);
  });

  const handleNumpadEnter = useCallback(() => {}, []);

  // ── Order management actions ──
  const handleEditOrder = useStableCallback(() => {
    // Open edit dialog/drawer for customer, guests, notes, service type
    om.editOrder?.();
  });

  const handleCancelOrder = useStableCallback(() => {
    om.cancelOrder?.();
  });

  const handleDeleteOrder = useStableCallback(() => {
    if (!om.currentOrderName) return;
    frappe.confirm(
      __("Void order {0}? Only orders with nothing sent to the kitchen can be voided.", [om.currentOrderName]),
      () => om.deleteOrder()
    );
  });

  // Print the pre-bill (Order Account print format) for the customer
  const handleAccount = useStableCallback(async () => {
    if (!om.currentOrderName) return;
    await om.waitForSync();
    const params = new URLSearchParams({
      doctype: "Table Order",
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
  const canDiscount = canEdit && posData?.allowDiscountChange;
  const canRate     = canEdit && posData?.allowRateChange;

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

  const Mobile = (
    <div className="flex flex-col h-full overflow-hidden bg-card text-card-foreground">
      {/* ── Order Tabs (always visible) ── */}
      <OrderTabs {...orderTabsProps} />

      <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
        {mobileTab === "items" && (
          <ItemCatalog onItemClick={handleItemClick} />
        )}

        {mobileTab === "cart" && (
          <div className="flex-1 flex flex-col overflow-hidden">
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
          </div>
        )}
      </div>

      <MobileBottomTabs
        activeTab={mobileTab}
        onTabChange={setMobileTab}
        cartCount={om.itemsList.length}
      />
    </div>
  );

  const actionCustomer = () => {
    if (!om?.currentOrder?.name) return;
    MetaForm.save('Table Order', om.currentOrder.name, {
      title: __(`Update Customer`),
      fields: ['customer'],
      onSave: () => handleRefresh(),
    });
  }

  const Desk = (
    <div className="flex flex-col h-full overflow-hidden bg-card text-card-foreground">

      {/* ── Order Tabs (full width) ── */}
      

      {/* ── 2-panel body ── */}
      <div className="flex flex-1 min-h-0">
        <main className="flex-1 flex flex-col min-w-0 border-r border-border">
          <ItemCatalog onItemClick={handleItemClick} />
        </main>

        <aside className="w-[380px] shrink-0 flex flex-col">
          <button 
            onClick={actionCustomer} 
            className="shrink-0 flex items-center gap-1.5 px-3.5 py-1.5 text-md font-semibold whitespace-nowrap transition-all bg-indigo-500/15 text-indigo-400 border-b border-indigo-500/60"
          >
            <span className="link">
              {om.currentOrder?.customer_name || om.currentOrder?.customer || table.customer || __('Guest')}
            </span>
          </button>
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
    <Modal size="full" compactHeader={true} hasReturn={false} title={(
      <div className="flex flex-row">
        <div className="group !bg-primary/40 relative flex items-center gap-1.5 px-3 py-1.5 text-lg font-medium transition-all min-w-0  shrink-0 bg-transparent text-foreground hover:bg-muted/50">
          <span>{title}</span>
        </div> 
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

  /* const title = table
    ? `${table.room?.description || ""} (${table.description || ""}) ${table.customer || ""}`
    : __("Order Manager"); */

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