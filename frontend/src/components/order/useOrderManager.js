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
import { isEditable } from "./statuses";
import { getUrlParam, setUrlParams } from "@/utils/urlState";
import { useState, useCallback, useRef, useEffect, useMemo, useTransition } from "react";
import OrderAPI, { CLIENT_ID } from "./api";
import {
  calculateItem,
  updateItemField,
  aggregateOrder,
  applyPricingRules,
  flt,
} from "./orderItems/calculator";

import { modifiersKey, sumModifiers } from "./modifierRules";
export { modifiersKey, sumModifiers };

let _counter = 0;

function newIdentifier() {
  return `entry_${Date.now()}_${++_counter}`;
}

// Statuses the waiter can still edit come from the server (Ren Order Status
// "Allows to edit Item"); see statuses.js. "Sent" items can only be removed
// by managers (enforced by the server too).
// Sent lines can be voided by anyone: the server asks for a manager PIN when
// the person's role doesn't allow voids.
function isDeletable(status) {
  return isEditable(status) || status === "Sent";
}


export default function useOrderManager({ tableName, posData }) {
  // ═══════════════════════════════════════════════
  // STATE — Only what MUST trigger re-renders
  // ═══════════════════════════════════════════════

  const [orders, setOrders] = useState([]);
  const [currentOrderName, setCurrentOrderName] = useState(null);
  const [items, setItems] = useState({});

  // Latest items, updated synchronously. Every write goes through
  // setItemsSync so callers can read the result immediately (e.g. to queue
  // the server save). Relying on a setState updater having run doesn't
  // work: React may defer it, and the change would never be saved.
  const itemsRef = useRef({});
  const setItemsSync = useCallback((updater) => {
    const next = typeof updater === "function" ? updater(itemsRef.current) : updater;
    if (next !== itemsRef.current) {
      itemsRef.current = next;
      setItems(next);
    }
    return next;
  }, []);
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

  // Resolvers waiting for the save queue to drain (see waitForSync).
  const syncWaitersRef = useRef([]);

  // Debounce timer for realtime refresh
  const realtimeTimerRef = useRef(null);

  const currentOrderNameRef = useRef(currentOrderName);
  currentOrderNameRef.current = currentOrderName;

  const currentItemIdRef = useRef(currentItemId);
  currentItemIdRef.current = currentItemId;

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

  // held lines (the next course) wait for Fire; Send leaves them
  const heldCount = useMemo(
    () => itemsList.filter((i) => isEditable(i.status) && i.ren_hold).length,
    [itemsList]
  );
  const pendingCount = useMemo(
    () => itemsList.filter((i) => isEditable(i.status) && !i.ren_hold).length,
    [itemsList]
  );

  // Tabs: the open order's badge follows what the waiter is doing right now.
  // While another order is loading, the items on screen are still the
  // previous order's (their `parent`), so its badge keeps the server count.
  const ordersWithCounts = useMemo(() => {
    const mine = itemsList.every((i) => !i.parent || i.parent === currentOrderName);
    if (!mine) return orders;
    return orders.map((o) => (o.name === currentOrderName
      ? { ...o, items_count: itemsList.length, pending_count: pendingCount }
      : o));
  }, [orders, currentOrderName, itemsList, pendingCount]);
  const countsRef = useRef({});
  useEffect(() => {
    const mine = itemsList.every((i) => !i.parent || i.parent === currentOrderName);
    if (mine && currentOrderName) {
      countsRef.current = { order: currentOrderName, items_count: itemsList.length, pending_count: pendingCount };
    }
  }, [currentOrderName, itemsList, pendingCount]);

  // ═══════════════════════════════════════════════
  // SERVER SYNC — Ref-based, zero re-renders
  // ═══════════════════════════════════════════════

  // The server is the source of truth for prices: if it corrected an
  // item (price list, discount not allowed, pricing rule), show its values.
  // Only price fields are taken, so a qty typed meanwhile is kept.
  const applyServerItem = useCallback((serverItem) => {
    if (!serverItem?.identifier) return;
    setItemsSync((prev) => {
      const cur = prev[serverItem.identifier];
      if (!cur) return prev;
      const same = ["price_list_rate", "discount_percentage", "rate"].every(
        (k) => Math.abs(flt(cur[k]) - flt(serverItem[k])) < 0.005
      ) && (cur.item_tax_rate || "{}") === (serverItem.item_tax_rate || "{}")
        && modifiersKey(cur.modifiers) === modifiersKey(serverItem.modifiers)
        && Math.abs(flt(cur.modifiers_amount) - flt(serverItem.modifiers_amount)) < 0.005;
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
            modifiers: serverItem.modifiers || [],
            modifiers_amount: serverItem.modifiers_amount || 0,
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
          await OrderAPI.deleteItem(job.orderName, job.identifier, job.voidInfo);
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
    const waiters = syncWaitersRef.current;
    syncWaitersRef.current = [];
    waiters.forEach((resolve) => resolve());
  }, [applyServerItem]);

  /** Resolves once every queued item change has reached the server. */
  const waitForSync = useCallback(() => {
    if (!savingRef.current && saveQueue.current.length === 0) return Promise.resolve();
    return new Promise((resolve) => syncWaitersRef.current.push(resolve));
  }, []);
  const waitForSyncRef = useRef(waitForSync);

  const queueSave = useCallback((orderName, item) => {
    saveQueue.current.push({ type: "save", orderName, item });
    processSaveQueue();
  }, [processSaveQueue]);

  const queueDelete = useCallback((orderName, identifier, voidInfo) => {
    saveQueue.current.push({ type: "delete", orderName, identifier, voidInfo });
    processSaveQueue();
  }, [processSaveQueue]);

  // ═══════════════════════════════════════════════
  // ORDER OPERATIONS
  // ═══════════════════════════════════════════════

  const selectOrder = useCallback(async (orderName) => {
    // the order we leave keeps the counts it had on screen
    const leaving = countsRef.current;
    if (leaving.order && leaving.order !== orderName) {
      setOrders((prev) => prev.map((o) => (o.name === leaving.order
        ? { ...o, items_count: leaving.items_count, pending_count: leaving.pending_count }
        : o)));
    }
    // Urgent: highlight the order tab immediately
    setCurrentOrderName(orderName);
    setUrlParams({ order: orderName });
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
        setItemsSync(itemsMap);
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
        // the order open before a reload (?order=…), else the server's pick / the last one
        const fromUrl = getUrlParam("order");
        const target = (fromUrl && ordersList.some((o) => o.name === fromUrl) && fromUrl)
          || result?.order || ordersList[ordersList.length - 1]?.name;
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

  // voidInfo {reason, note}: required by the server when items were sent
  const deleteOrder = useCallback(async (voidInfo) => {
    const orderName = currentOrderNameRef.current;
    if (!orderName) return;
    try {
      await waitForSyncRef.current?.();
      await OrderAPI.deleteOrder(orderName, voidInfo);
      setOrders((prev) => prev.filter((o) => o.name !== orderName));
      setItemsSync({});
      setCurrentItemId(null);
      setCurrentOrderName(null);
    } catch (err) {
      console.error("Failed to delete order:", err);
    }
  }, []);

  // ═══════════════════════════════════════════════
  // ITEM OPERATIONS — All stable identity
  // ═══════════════════════════════════════════════

  // First item on a table without an open order creates the order.
  const creatingOrderRef = useRef(false);
  const pendingFirstItemsRef = useRef([]);
  const pushItemRef = useRef(null);

  const pushItem = useCallback((menuItem) => {
    const orderName = currentOrderNameRef.current;
    if (!orderName) {
      if (!tableName) return;
      pendingFirstItemsRef.current.push(menuItem);
      if (creatingOrderRef.current) return;
      creatingOrderRef.current = true;
      OrderAPI.addOrder(tableName)
        .then((result) => {
          const orderData = result?.order?.data || result?.order || result;
          if (!orderData?.name) return;
          setOrders((prev) => [...prev, orderData]);
          currentOrderNameRef.current = orderData.name;
          setCurrentOrderName(orderData.name);
          setItemsSync({});
          const queued = pendingFirstItemsRef.current.splice(0);
          queued.forEach((mi) => pushItemRef.current?.(mi));
        })
        .catch((err) => {
          pendingFirstItemsRef.current = [];
          console.error("Failed to create order:", err);
        })
        .finally(() => { creatingOrderRef.current = false; });
      return;
    }

    const ti = taxInclusiveRef.current;
    const pd = posDataRef.current;
    let sideEffects = null;

    setItemsSync((prev) => {
      // same dish with the same options -> one line with more qty
      const key = modifiersKey(menuItem.modifiers);
      const existing = Object.values(prev).find(
        (i) => i.item_code === menuItem.item_code && isEditable(i.status) && !i.ren_hold
          && modifiersKey(i.modifiers) === key && !i.notes
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
        process_status_data: menuItem.process_status_data || {
          icon: "fa fa-cart-plus",
          color: "orange",
        },
      };

      if (pd?.pricingRules?.length) {
        newItem = applyPricingRules(newItem, pd.pricingRules);
      }

      // options: their extra price goes on top of the (rule) base price
      const mods = menuItem.modifiers || [];
      const modsAmount = sumModifiers(mods);
      newItem = {
        ...newItem,
        modifiers: mods,
        modifiers_amount: modsAmount,
        price_list_rate: Math.max(flt(newItem.price_list_rate) + modsAmount, 0),
      };

      const updated = calculateItem(newItem, { taxInclusive: ti });
      sideEffects = { identifier, item: updated };
      return { ...prev, [identifier]: updated };
    });

    if (sideEffects) {
      setCurrentItemId(sideEffects.identifier);
      queueSave(orderName, sideEffects.item);
    }
  }, [queueSave, tableName]);
  pushItemRef.current = pushItem;

  // Change the options of a line not sent yet; the base price is kept.
  const setItemModifiers = useCallback((identifier, modifiers) => {
    const orderName = currentOrderNameRef.current;
    const ti = taxInclusiveRef.current;
    let saved = null;
    setItemsSync((prev) => {
      const item = prev[identifier];
      if (!item || !isEditable(item.status)) return prev;
      const base = flt(item.price_list_rate) - flt(item.modifiers_amount);
      const amount = sumModifiers(modifiers);
      saved = calculateItem(
        { ...item, modifiers, modifiers_amount: amount, price_list_rate: Math.max(base + amount, 0), status: "Pending" },
        { taxInclusive: ti }
      );
      return { ...prev, [identifier]: saved };
    });
    if (saved) queueSave(orderName, saved);
  }, [queueSave]);

  // hold a line not sent yet for a later course, or release it
  const toggleHold = useCallback((identifier) => {
    const orderName = currentOrderNameRef.current;
    let saved = null;
    setItemsSync((prev) => {
      const item = prev[identifier];
      if (!item || !isEditable(item.status)) return prev;
      saved = { ...item, ren_hold: item.ren_hold ? 0 : 1 };
      return { ...prev, [identifier]: saved };
    });
    if (saved) queueSave(orderName, saved);
  }, [queueSave]);

  const updateItem = useCallback((identifier, field, value) => {
    const orderName = currentOrderNameRef.current;
    const ti = taxInclusiveRef.current;
    let sideEffects = null;

    setItemsSync((prev) => {
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

  // voidInfo {reason, note}: for items already sent to the kitchen
  const deleteItem = useCallback((identifier, voidInfo) => {
    const orderName = currentOrderNameRef.current;
    let shouldSync = false;

    setItemsSync((prev) => {
      const item = prev[identifier];
      if (!item || !isDeletable(item.status, posDataRef.current?.isManager)) return prev;
      shouldSync = true;
      const newItems = { ...prev };
      delete newItems[identifier];
      return newItems;
    });

    if (shouldSync) {
      setCurrentItemId((prev) => (prev === identifier ? null : prev));
      queueDelete(orderName, identifier, voidInfo);
    }
  }, [queueDelete]);

  const updateItemNotes = useCallback((identifier, notes) => {
    const orderName = currentOrderNameRef.current;
    let updatedItem = null;

    setItemsSync((prev) => {
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

  // fire = send the held lines (the next course) instead of the rest
  const sendOrder = useCallback(async (fire = false) => {
    const orderName = currentOrderNameRef.current;
    if (!orderName) return;
    fire = fire === true;

    // Guard: check if there are actually lines to send
    const currentItems = Object.values(itemsRef.current);
    const hasPending = currentItems.some(
      (i) => isEditable(i.status) && flt(i.qty) > 0 && !!i.ren_hold === fire
    );
    if (!hasPending) return;

    // pending item saves must reach the server before the kitchen gets the order
    await waitForSync();
    syncingRef.current = true;
    try {
      const result = await OrderAPI.sendOrder(orderName, fire);
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
          setItemsSync(itemsMap);
        });
      }
    } catch (err) {
      console.error("Failed to send order:", err);
    }
    syncingRef.current = false;
  }, [startItemsTransition, waitForSync]);

  const transferOrder = useCallback(async (targetTable) => {
    const orderName = currentOrderNameRef.current;
    if (!orderName) return;
    await waitForSync();
    await OrderAPI.transferOrder(orderName, targetTable);
    // the order left this table
    reloadRef.current?.({ preserveSelection: false, silent: false });
  }, [waitForSync]);

  /** Split: map = { identifier: { qty } } moved into a new order. */
  const divideOrder = useCallback(async (map) => {
    const orderName = currentOrderNameRef.current;
    if (!orderName) return;
    await waitForSync();
    const res = await OrderAPI.divideOrder(orderName, map);
    await reloadRef.current?.({ preserveSelection: true, silent: true });
    const newName = res?.new_order?.data?.name;
    if (newName) selectOrder(newName);
  }, [waitForSync, selectOrder]);

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

    // order_update is published to the "Ren Order" doctype room
    frappe.realtime.doctype_subscribe?.("Ren Order");
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
    orders: ordersWithCounts,
    currentOrder,
    currentOrderName,
    items,
    itemsList,
    currentItem,
    currentItemId,
    totals,
    pendingCount,
    heldCount,
    toggleHold,
    loading,
    isItemsPending,
    get syncing() { return syncingRef.current; },

    addOrder,
    selectOrder,
    deleteOrder,
    sendOrder,
    transferOrder,
    divideOrder,
    setCustomer,
    setDinners,

    pushItem,
    updateItem,
    deleteItem,
    updateItemNotes,
    setItemModifiers,
    setCurrentItemId,

    isItemEditable,
    isItemDeletable,
    loadOrders,
    waitForSync,
  };
}