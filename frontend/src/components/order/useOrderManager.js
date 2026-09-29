/**
 * useOrderManager — Core state management for order operations.
 *
 * KEY FIXES (v3):
 * ─────────────────────────────────────────────────
 * 1. loadOrders has `silent` mode — background refreshes
 *    do NOT set loading=true, so the Order component doesn't
 *    return the <Loader2> and destroy the entire tree.
 *
 * 2. Own-event suppression via epoch ref — after every
 *    server write we set a suppression window. Realtime
 *    events arriving within that window are ignored.
 *    This replaces the fragile `data.source === user` check.
 *
 * 3. Realtime handler is debounced — rapid-fire events
 *    (e.g. multiple items saved) coalesce into one refresh.
 *
 * 4. syncing is ref-only (no renders).
 * 5. All derived state memoized.
 * 6. All callbacks stable via refs.
 */
import { useState, useCallback, useRef, useEffect, useMemo, useTransition } from "react";
import OrderAPI, { CLIENT_ID } from "./api";
import {
  calculateItem,
  updateItemField,
  aggregateOrder,
  applyPricingRules,
  flt,
} from "./orderItems/calculator";

let _counter = 0;
function newIdentifier() {
  return `entry_${Date.now()}_${++_counter}`;
}

const EDITABLE_STATUSES = ["Pending", "Attending", null, undefined, ""];
// "Sent" items can only be removed by managers (enforced by the server too)
const DELETABLE_STATUSES = ["Pending", "Attending", null, undefined, ""];

function isEditable(status) {
  return EDITABLE_STATUSES.includes(status);
}
function isDeletable(status, isManager = false) {
  return DELETABLE_STATUSES.includes(status) || (isManager && status === "Sent");
}


export default function useOrderManager({ tableName, posData, onClose }) {
  // ═══════════════════════════════════════════════
  // STATE — Only what MUST trigger re-renders
  // ═══════════════════════════════════════════════

  const [orders, setOrders] = useState([]);
  const [currentOrderName, setCurrentOrderName] = useState(null);
  const [items, setItems] = useState({});
  const [currentItemId, setCurrentItemId] = useState(null);
  const [loading, setLoading] = useState(false);

  // Low-priority transition for switching order items.
  // While isPending, old items stay visible with a subtle fade,
  // and React can interrupt the render if user clicks another order.
  const [isItemsPending, startItemsTransition] = useTransition();

  // ═══════════════════════════════════════════════
  // REFS — Non-reactive values
  // ═══════════════════════════════════════════════

  const syncingRef = useRef(false);
  const saveQueue = useRef([]);
  const savingRef = useRef(false);

  // Set once loadOrders exists; lets the save queue resync after a failure.
  const reloadRef = useRef(null);

  // Debounce timer for realtime refresh
  const realtimeTimerRef = useRef(null);

  const currentOrderNameRef = useRef(currentOrderName);
  currentOrderNameRef.current = currentOrderName;

  const currentItemIdRef = useRef(currentItemId);
  currentItemIdRef.current = currentItemId;

  const itemsRef = useRef(items);
  itemsRef.current = items;

  const taxInclusive = posData?.taxInclusive || false;
  const taxInclusiveRef = useRef(taxInclusive);
  taxInclusiveRef.current = taxInclusive;

  const posDataRef = useRef(posData);
  posDataRef.current = posData;

  // ═══════════════════════════════════════════════
  // MEMOIZED DERIVED STATE
  // ═══════════════════════════════════════════════

  const currentOrder = useMemo(
    () => orders.find((o) => o.name === currentOrderName) || null,
    [orders, currentOrderName]
  );

  const currentItem = useMemo(
    () => (currentItemId ? items[currentItemId] ?? null : null),
    [items, currentItemId]
  );

  const itemsList = useMemo(
    () => Object.values(items).filter((i) => flt(i.qty) > 0),
    [items]
  );

  const totals = useMemo(
    () => aggregateOrder(itemsList, currentOrder || {}),
    [itemsList, currentOrder]
  );

  const pendingCount = useMemo(
    () => itemsList.filter((i) => isEditable(i.status)).length,
    [itemsList]
  );

  // ═══════════════════════════════════════════════
  // SERVER SYNC — Ref-based, zero re-renders
  // ═══════════════════════════════════════════════

  // The server is the source of truth for prices: if it corrected an
  // item (price list, discount not allowed, pricing rule), show its values.
  // Only price fields are taken, so a qty typed meanwhile is kept.
  const applyServerItem = useCallback((serverItem) => {
    if (!serverItem?.identifier) return;
    setItems((prev) => {
      const cur = prev[serverItem.identifier];
      if (!cur) return prev;
      const same = ["price_list_rate", "discount_percentage", "rate"].every(
        (k) => Math.abs(flt(cur[k]) - flt(serverItem[k])) < 0.005
      ) && (cur.item_tax_rate || "{}") === (serverItem.item_tax_rate || "{}");
      if (same) return prev;
      return {
        ...prev,
        [serverItem.identifier]: calculateItem(
          {
            ...cur,
            price_list_rate: serverItem.price_list_rate,
            discount_percentage: serverItem.discount_percentage,
            rate: serverItem.rate,
            item_tax_rate: serverItem.item_tax_rate,
          },
          { taxInclusive: taxInclusiveRef.current }
        ),
      };
    });
  }, []);

  const processSaveQueue = useCallback(async () => {
    if (savingRef.current) return;
    savingRef.current = true;
    syncingRef.current = true;

    while (saveQueue.current.length > 0) {
      const job = saveQueue.current.shift();
      try {
        if (job.type === "save") {
          const res = await OrderAPI.pushItem(job.orderName, job.item);
          applyServerItem(res?.item);
        } else if (job.type === "delete") {
          await OrderAPI.deleteItem(job.orderName, job.identifier);
        }
      } catch (err) {
        // The server rejected or corrected the change: tell the user and
        // reload the server state so the screen matches what was saved.
        console.error("Sync failed:", err);
        frappe.show_alert({ message: __("Change not saved, reloading order"), indicator: "red" });
        saveQueue.current = [];
        reloadRef.current?.({ preserveSelection: true, silent: true });
      }
    }

    savingRef.current = false;
    syncingRef.current = false;
  }, [applyServerItem]);

  const queueSave = useCallback((orderName, item) => {
    saveQueue.current.push({ type: "save", orderName, item });
    processSaveQueue();
  }, [processSaveQueue]);

  const queueDelete = useCallback((orderName, identifier) => {
    saveQueue.current.push({ type: "delete", orderName, identifier });
    processSaveQueue();
  }, [processSaveQueue]);

  // ═══════════════════════════════════════════════
  // ORDER OPERATIONS
  // ═══════════════════════════════════════════════

  const selectOrder = useCallback(async (orderName) => {
    // Urgent: highlight the order tab immediately
    setCurrentOrderName(orderName);
    // NOTE: We do NOT clear currentItemId or items here.
    // Old data stays visible (with isPending fade) while new data loads.
    // Both items + selection change atomically inside the transition.

    try {
      const result = await OrderAPI.getItems(orderName);

      if (result?.order) {
        setOrders((prev) =>
          prev.map((o) =>
            o.name === orderName
              ? { ...o, ...(result.order.data || result.order) }
              : o
          )
        );
      }

      const serverItems = result?.items || [];
      const ti = taxInclusiveRef.current;
      const itemsMap = {};
      for (const item of serverItems) {
        itemsMap[item.identifier] = calculateItem(item, { taxInclusive: ti });
      }

      // Low-priority: swap items + selection atomically.
      // React keeps showing old data until this commits.
      // If user clicks another order mid-render, React aborts this one.
      startItemsTransition(() => {
        setItems(itemsMap);
        setCurrentItemId(
          serverItems.length > 0 ? serverItems[0].identifier : null
        );
      });
    } catch (err) {
      console.error("Failed to load items:", err);
    }
  }, [startItemsTransition]);

  /**
   * Load orders for the current table.
   *
   * @param {Object} opts
   * @param {boolean} opts.preserveSelection - Keep current order selected
   * @param {boolean} opts.silent - If true, do NOT set loading=true.
   *   This prevents the Order component from returning the <Loader2>
   *   spinner and destroying the entire component tree.
   *   Used for background refreshes (realtime events).
   */
  const loadOrders = useCallback(async (optsOrPreserve = {}) => {
    // Support both old positional API: loadOrders(true)
    // and new object API: loadOrders({ preserveSelection: true, silent: true })
    const opts = typeof optsOrPreserve === "boolean"
      ? { preserveSelection: optsOrPreserve, silent: false }
      : optsOrPreserve;

    const { preserveSelection = false, silent = false } = opts;
    if (!tableName) return;

    if (!silent) {
      setLoading(true);
    }

    try {
      const result = await OrderAPI.getOrders(tableName);
      const ordersList = (result?.orders || []).map((o) => o.data || o);
      setOrders(ordersList);

      if (!preserveSelection) {
        const target = result?.order || ordersList[ordersList.length - 1]?.name;
        if (target) {
          selectOrder(target);
        }
      }
    } catch (err) {
      console.error("Failed to load orders:", err);
    }

    if (!silent) {
      setLoading(false);
    }
  }, [tableName, selectOrder]);
  reloadRef.current = loadOrders;

  const addOrder = useCallback(async () => {
    if (!tableName) return;
    // NOTE: No setLoading(true) here — that would unmount the entire
    // component tree (shows <Loader2> spinner) and remount on finish.
    // addOrder is fast enough to not need a full-screen spinner.
    try {
      const result = await OrderAPI.addOrder(tableName);
      if (result) {
        const orderData = result.order?.data || result.order || result;
        setOrders((prev) => [...prev, orderData]);
        selectOrder(orderData.name);
      }
    } catch (err) {
      console.error("Failed to add order:", err);
    }
  }, [tableName, selectOrder]);

  const deleteOrder = useCallback(async () => {
    const orderName = currentOrderNameRef.current;
    if (!orderName) return;
    try {
      await OrderAPI.deleteOrder(orderName);
      setOrders((prev) => prev.filter((o) => o.name !== orderName));
      setItems({});
      setCurrentItemId(null);
      setCurrentOrderName(null);
    } catch (err) {
      console.error("Failed to delete order:", err);
    }
  }, []);

  // ═══════════════════════════════════════════════
  // ITEM OPERATIONS — All stable identity
  // ═══════════════════════════════════════════════

  const pushItem = useCallback((menuItem) => {
    const orderName = currentOrderNameRef.current;
    if (!orderName) {
      frappe.show_alert({
        message: __("Please select or create an order"),
        indicator: "orange",
      });
      return;
    }

    const ti = taxInclusiveRef.current;
    const pd = posDataRef.current;
    let sideEffects = null;

    setItems((prev) => {
      const existing = Object.values(prev).find(
        (i) => i.item_code === menuItem.item_code && isEditable(i.status)
      );

      if (existing) {
        const newItem = {
          ...existing,
          qty: flt(existing.qty) + (menuItem.qty || 1),
          status: "Pending",
        };
        const updated = calculateItem(newItem, { taxInclusive: ti });
        sideEffects = { identifier: existing.identifier, item: updated };
        return { ...prev, [existing.identifier]: updated };
      }

      const identifier = newIdentifier();
      let newItem = {
        identifier,
        item_code: menuItem.item_code,
        item_name: menuItem.item_name,
        item_group: menuItem.item_group,
        price_list_rate: flt(menuItem.price_list_rate || menuItem.rate),
        rate: flt(menuItem.price_list_rate || menuItem.rate),
        qty: menuItem.qty || 1,
        discount_percentage: 0,
        item_tax_rate: menuItem.item_tax_rate || "{}",
        status: "Pending",
        notes: "",
        has_batch_no: menuItem.has_batch_no || 0,
        has_serial_no: menuItem.has_serial_no || 0,
        batch_no: "",
        serial_no: "",
        image: menuItem.image || "",
        is_customizable: menuItem.is_customizable || 0,
        process_status_data: menuItem.process_status_data || {
          icon: "fa fa-cart-plus",
          color: "orange",
        },
      };

      if (pd?.pricingRules?.length) {
        newItem = applyPricingRules(newItem, pd.pricingRules);
      }

      const updated = calculateItem(newItem, { taxInclusive: ti });
      sideEffects = { identifier, item: updated };
      return { ...prev, [identifier]: updated };
    });

    if (sideEffects) {
      setCurrentItemId(sideEffects.identifier);
      queueSave(orderName, sideEffects.item);
    }
  }, [queueSave]);

  const updateItem = useCallback((identifier, field, value) => {
    const orderName = currentOrderNameRef.current;
    const ti = taxInclusiveRef.current;
    let sideEffects = null;

    setItems((prev) => {
      const item = prev[identifier];
      if (!item || !isEditable(item.status)) return prev;

      const updated = updateItemField(item, field, value, { taxInclusive: ti });

      if (flt(updated.qty) <= 0) {
        if (isDeletable(item.status, posDataRef.current?.isManager)) {
          const newItems = { ...prev };
          delete newItems[identifier];
          sideEffects = { type: "delete", identifier };
          return newItems;
        }
        return prev;
      }

      sideEffects = { type: "save", item: updated };
      return { ...prev, [identifier]: updated };
    });

    if (sideEffects?.type === "delete") {
      setCurrentItemId((prev) => (prev === identifier ? null : prev));
      queueDelete(orderName, identifier);
    } else if (sideEffects?.type === "save") {
      queueSave(orderName, sideEffects.item);
    }
  }, [queueSave, queueDelete]);

  const deleteItem = useCallback((identifier) => {
    const orderName = currentOrderNameRef.current;
    let shouldSync = false;

    setItems((prev) => {
      const item = prev[identifier];
      if (!item || !isDeletable(item.status, posDataRef.current?.isManager)) return prev;
      shouldSync = true;
      const newItems = { ...prev };
      delete newItems[identifier];
      return newItems;
    });

    if (shouldSync) {
      setCurrentItemId((prev) => (prev === identifier ? null : prev));
      queueDelete(orderName, identifier);
    }
  }, [queueDelete]);

  const updateItemNotes = useCallback((identifier, notes) => {
    const orderName = currentOrderNameRef.current;
    let updatedItem = null;

    setItems((prev) => {
      const item = prev[identifier];
      if (!item) return prev;
      const updated = { ...item, notes };
      updatedItem = updated;
      return { ...prev, [identifier]: updated };
    });

    if (updatedItem) {
      queueSave(orderName, updatedItem);
    }
  }, [queueSave]);

  // ═══════════════════════════════════════════════
  // ORDER ACTIONS
  // ═══════════════════════════════════════════════

  const sendOrder = useCallback(async () => {
    const orderName = currentOrderNameRef.current;
    if (!orderName) return;

    // Guard: check if there are actually pending items
    const currentItems = Object.values(itemsRef.current);
    const hasPending = currentItems.some(
      (i) => isEditable(i.status) && flt(i.qty) > 0
    );
    if (!hasPending) return;

    syncingRef.current = true;
    try {
      const result = await OrderAPI.sendOrder(orderName);
      const ti = taxInclusiveRef.current;

      if (result?.order) {
        const orderData = result.order.data || result.order;
        setOrders((prev) =>
          prev.map((o) =>
            o.name === orderName ? { ...o, ...orderData } : o
          )
        );
      }

      if (result?.items) {
        const itemsMap = {};
        for (const item of result.items) {
          itemsMap[item.identifier] = calculateItem(item, { taxInclusive: ti });
        }
        // Low-priority: status icons transition (Pending → Sent).
        // The "Order" button feedback is already instant.
        startItemsTransition(() => {
          setItems(itemsMap);
        });
      }
    } catch (err) {
      console.error("Failed to send order:", err);
    }
    syncingRef.current = false;
  }, [startItemsTransition]);

  const transferOrder = useCallback(async (targetTable) => {
    const orderName = currentOrderNameRef.current;
    if (!orderName) return;
    try {
      await OrderAPI.transferOrder(orderName, targetTable);
      setOrders((prev) => prev.filter((o) => o.name !== orderName));
      setItems({});
      setCurrentItemId(null);
      setCurrentOrderName(null);
    } catch (err) {
      console.error("Failed to transfer:", err);
    }
  }, []);

  const setCustomer = useCallback(async (customer) => {
    const orderName = currentOrderNameRef.current;
    if (!orderName) return;
    try {
      await OrderAPI.setCustomer(orderName, customer);
      setOrders((prev) =>
        prev.map((o) =>
          o.name === orderName ? { ...o, customer } : o
        )
      );
    } catch (err) {
      console.error("Failed to set customer:", err);
    }
  }, []);

  const setDinners = useCallback(async (dinners) => {
    const orderName = currentOrderNameRef.current;
    if (!orderName) return;
    try {
      await OrderAPI.setDinners(orderName, dinners);
      setOrders((prev) =>
        prev.map((o) =>
          o.name === orderName ? { ...o, dinners } : o
        )
      );
    } catch (err) {
      console.error("Failed to set dinners:", err);
    }
  }, []);

  // ─── Helpers ───────────────────────────────────

  const isItemEditable = useCallback(
    (identifier) => {
      const item = items[identifier];
      return item && isEditable(item.status);
    },
    [items]
  );

  const isItemDeletable = useCallback(
    (identifier) => {
      const item = items[identifier];
      return item && isDeletable(item.status, posDataRef.current?.isManager);
    },
    [items]
  );

  // ═══════════════════════════════════════════════
  // REALTIME LISTENER
  //   1) Own echo — the server returns the client_id of the tab that made
  //      the change; this tab ignores its own events.
  //   2) Debounce — multiple rapid events coalesce into
  //      one background refresh (silent: true).
  // ═══════════════════════════════════════════════

  useEffect(() => {
    const handler = (data) => {
      if (data?.table !== tableName) return;

      // Own echo: this tab made the change
      if (data?.client_id && data.client_id === CLIENT_ID) return;

      // Debounce rapid events
      if (realtimeTimerRef.current) {
        clearTimeout(realtimeTimerRef.current);
      }

      realtimeTimerRef.current = setTimeout(() => {
        realtimeTimerRef.current = null;

        if (
          data?.action === "delete" &&
          data?.order === currentOrderNameRef.current
        ) {
          // Our current order was deleted by someone else — full reload
          loadOrders({ preserveSelection: false, silent: false });
        } else {
          // Background refresh — SILENT, no loading state, no tree destruction
          loadOrders({ preserveSelection: true, silent: true });
        }
      }, 300);
    };

    // order_update is published to the "Table Order" doctype room
    frappe.realtime.doctype_subscribe?.("Table Order");
    frappe.realtime.on("order_update", handler);
    return () => {
      frappe.realtime.off("order_update", handler);
      if (realtimeTimerRef.current) {
        clearTimeout(realtimeTimerRef.current);
      }
    };
  }, [tableName, loadOrders]);

  // ─── Initial load ──────────────────────────────
  useEffect(() => {
    loadOrders({ preserveSelection: false, silent: false });
  }, [loadOrders]);

  return {
    orders,
    currentOrder,
    currentOrderName,
    items,
    itemsList,
    currentItem,
    currentItemId,
    totals,
    pendingCount,
    loading,
    isItemsPending,
    get syncing() { return syncingRef.current; },

    addOrder,
    selectOrder,
    deleteOrder,
    sendOrder,
    transferOrder,
    setCustomer,
    setDinners,

    pushItem,
    updateItem,
    deleteItem,
    updateItemNotes,
    setCurrentItemId,

    isItemEditable,
    isItemDeletable,
    loadOrders,
  };
}