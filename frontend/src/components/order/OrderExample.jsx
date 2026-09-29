import { useState, useCallback } from "react";
import { OrderSidebar } from "./src/OrderSidebar";
import { OrderDrawer } from "./src/OrderDrawer";

/**
 * OrderManagerExample — Shows how to wire OrderSidebar + OrderDrawer together.
 *
 * This is a reference implementation. Adapt to your actual OrderManager.
 *
 * Flow:
 *   ⋮ → "Details"   → opens OrderDrawer
 *   ⋮ → "Delete"    → confirm dialog → delete order
 *   ⋮ → "Duplicate"  → creates copy of order
 *   ⋮ → "Transfer"  → (your transfer table logic)
 */
export function OrderManagerExample({ orders, currentOrder, onSelectOrder, onAddOrder }) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(null);

  // ── Handle actions from OrderTab ⋮ menu ──
  const handleOrderAction = useCallback((action, order) => {
    switch (action) {
      case "details":
        // Select the order first, then open drawer
        onSelectOrder(order.name);
        setDrawerOpen(true);
        break;

      case "delete":
        setConfirmDelete(order);
        break;

      case "duplicate":
        duplicateOrder(order.name);
        break;

      case "transfer":
        // Open your table picker / transfer UI
        transferOrder(order.name);
        break;
    }
  }, [onSelectOrder]);

  // ── Delete order ──
  const handleDeleteConfirm = useCallback(async () => {
    if (!confirmDelete) return;
    try {
      await frappe.call({
        method: "frappe.client.delete",
        args: { doctype: "Table Order", name: confirmDelete.name },
      });
      frappe.show_alert({ message: __("Order deleted"), indicator: "green" });
      setConfirmDelete(null);
      // Refresh your orders list here
    } catch (err) {
      console.error("Delete failed:", err);
      frappe.show_alert({ message: __("Failed to delete order"), indicator: "red" });
    }
  }, [confirmDelete]);

  // ── Duplicate order ──
  const duplicateOrder = useCallback(async (orderName) => {
    try {
      const result = await frappe.call({
        method: "frappe.client.get",
        args: { doctype: "Table Order", name: orderName },
      });
      const doc = result.message;
      // Clear identity fields for new doc
      delete doc.name;
      delete doc.docstatus;
      delete doc.amended_from;
      delete doc.link_invoice;
      doc.status = null;
      doc.naming_series = "OR-.YYYY.-";
      doc.ordered_time = frappe.datetime.now_datetime();

      const saved = await frappe.call({
        method: "frappe.client.save",
        args: { doc: { ...doc, doctype: "Table Order" } },
      });
      frappe.show_alert({ message: __("Order duplicated"), indicator: "green" });
      onSelectOrder(saved.message.name);
      // Refresh your orders list here
    } catch (err) {
      console.error("Duplicate failed:", err);
      frappe.show_alert({ message: __("Failed to duplicate"), indicator: "red" });
    }
  }, [onSelectOrder]);

  // ── Transfer (placeholder) ──
  const transferOrder = useCallback((orderName) => {
    // Implement your table picker here
    // e.g., open a modal to select target table
    frappe.show_alert({ message: __("Transfer: implement table picker"), indicator: "blue" });
  }, []);

  // ── Update local order state after drawer edits ──
  const handleDrawerUpdate = useCallback((fieldname, value) => {
    // Update your local order state/store here
    // e.g., if using a state manager:
    // updateOrder(currentOrder.name, { [fieldname]: value });

    // Or if using React state:
    // setOrders(prev => prev.map(o =>
    //   o.name === currentOrder.name ? { ...o, [fieldname]: value } : o
    // ));
  }, [currentOrder]);

  return (
    <>
      {/* Sidebar with order tabs */}
      <OrderSidebar
        orders={orders}
        currentOrderName={currentOrder?.name}
        onSelectOrder={onSelectOrder}
        onAddOrder={onAddOrder}
        onOrderAction={handleOrderAction}
      />

      {/* Your main content area goes here */}
      {/* <ItemTree ... /> */}
      {/* <OrderSummary ... /> */}

      {/* Order details drawer */}
      <OrderDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        order={currentOrder}
        onUpdate={handleDrawerUpdate}
      />

      {/* Delete confirmation */}
      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-card rounded-xl p-5 shadow-xl max-w-sm w-full mx-4 border border-border">
            <p className="text-sm text-card-foreground mb-1">
              {__("Delete order {0}?", [confirmDelete.short_name || confirmDelete.name])}
            </p>
            <p className="text-xs text-muted-foreground mb-4">
              {__("This action cannot be undone.")}
            </p>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setConfirmDelete(null)}
                className="px-3 py-1.5 text-xs rounded-lg text-muted-foreground hover:bg-muted transition-colors"
              >
                {__("Cancel")}
              </button>
              <button
                onClick={handleDeleteConfirm}
                className="px-3 py-1.5 text-xs font-medium rounded-lg bg-destructive text-destructive-foreground
                           hover:bg-destructive/90 transition-colors"
              >
                {__("Delete")}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default OrderManagerExample;