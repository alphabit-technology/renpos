// hooks/useKitchen.js
import { useState, useEffect } from 'react';
import { useFrappeRealtime } from './useFrappeRealtime';

export function useKitchen(productionCenter) {
  const [pendingItems, setPendingItems] = useState([]);

  useEffect(() => {
    frappe.call({
      method: 'restaurant_management.api.get_pending_items',
      args: { production_center: productionCenter },
      callback: (r) => setPendingItems(r.message || [])
    });
  }, [productionCenter]);

  useFrappeRealtime('kitchen_order', (data) => {
    if (data.production_center === productionCenter) {
      if (data.action === 'new') {
        setPendingItems(prev => [...prev, ...data.items]);
      } else if (data.action === 'ready') {
        setPendingItems(prev => 
          prev.filter(item => item.name !== data.item_name)
        );
      }
    }
  }, [productionCenter]);

  const markReady = async (itemName) => {
    await frappe.call({
      method: 'restaurant_management.api.mark_item_ready',
      args: { item: itemName, client: RM.client }
    });
  };

  return { pendingItems, markReady };
}