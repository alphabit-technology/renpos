/**
 * OrderQtyStore — Fine-grained reactivity for item qty badges.
 *
 * Problem: Passing qtyMap as prop causes the entire ItemTree
 * (50+ ItemCards with images) to re-render on every qty change.
 *
 * Solution: Each ItemCard subscribes to ONLY its own item's qty.
 * When PIZZA-001 qty changes, only PIZZA-001's badge re-renders.
 * The other 49 cards don't touch the DOM. Images never reload.
 *
 * Pattern: React.createContext + useSyncExternalStore
 */
import { createContext, useContext, useRef, useCallback, useMemo } from 'react';
import { useSyncExternalStore } from 'react';

// ─── Store class ─────────────────────────────────

class QtyStore {
  constructor() {
    this._qty = {};        // { item_code: number }
    this._listeners = new Set();
  }

  /** Update the entire map (called from useOrderManager) */
  setAll(itemsList) {
    const next = {};
    for (const item of itemsList) {
      next[item.item_code] = (next[item.item_code] || 0) + (item.qty || 0);
    }

    // Only notify if something actually changed
    let changed = false;
    for (const code in next) {
      if (this._qty[code] !== next[code]) { changed = true; break; }
    }
    if (!changed) {
      for (const code in this._qty) {
        if (!(code in next)) { changed = true; break; }
      }
    }

    if (changed) {
      this._qty = next;
      this._notify();
    }
  }

  getQty(itemCode) {
    return this._qty[itemCode] || 0;
  }

  getSnapshot() {
    return this._qty;
  }

  subscribe(listener) {
    this._listeners.add(listener);
    return () => this._listeners.delete(listener);
  }

  _notify() {
    for (const fn of this._listeners) fn();
  }
}

// ─── Context ─────────────────────────────────────

const QtyStoreContext = createContext(null);

export function QtyStoreProvider({ children }) {
  const storeRef = useRef(null);
  if (!storeRef.current) {
    storeRef.current = new QtyStore();
  }

  return (
    <QtyStoreContext.Provider value={storeRef.current}>
      {children}
    </QtyStoreContext.Provider>
  );
}

// ─── Hooks ───────────────────────────────────────

/**
 * Get the store instance (used by OrderManager to push updates).
 *
 * Usage in OrderManager:
 *   const qtyStore = useQtyStore();
 *   useEffect(() => qtyStore.setAll(om.itemsList), [om.itemsList]);
 */
export function useQtyStore() {
  const store = useContext(QtyStoreContext);
  if (!store) throw new Error('useQtyStore must be inside QtyStoreProvider');
  return store;
}

/**
 * Subscribe to ONE item's qty. Only re-renders when THIS item's qty changes.
 *
 * Usage in ItemCard:
 *   const qty = useOrderQty("PIZZA-001");  // only re-renders if this changes
 */
export function useOrderQty(itemCode) {
  const store = useContext(QtyStoreContext);

  // Hooks can't be conditional: without a store, subscribe to nothing.
  const subscribe = useCallback(
    (onStoreChange) => (store ? store.subscribe(onStoreChange) : () => {}),
    [store]
  );

  const getSnapshot = useCallback(
    () => (store ? store.getQty(itemCode) : 0),
    [store, itemCode]
  );

  return useSyncExternalStore(subscribe, getSnapshot);
}