// hooks/useOrders.js
import { useState, useEffect } from 'react';
import { useFrappeRealtime } from './useFrappeRealtime';

export function useOrders(tableId) {
  const [orders, setOrders] = useState([]);

  useEffect(() => {
    if (!tableId) return;
    
    frappe.call({
      method: 'restaurant_management.api.get_table_orders',
      args: { table: tableId },
      callback: (r) => setOrders(r.message || [])
    });
  }, [tableId]);

  useFrappeRealtime('order_update', (data) => {
    if (data.table === tableId) {
      if (data.action === 'new') {
        setOrders(prev => [...prev, data.order]);
      } else if (data.action === 'update') {
        setOrders(prev => prev.map(o => 
          o.name === data.order.name ? data.order : o
        ));
      } else if (data.action === 'delete') {
        setOrders(prev => prev.filter(o => o.name !== data.order.name));
      }
    }
  }, [tableId]);

  const addOrder = async (items) => {
    await frappe.call({
      method: 'restaurant_management.api.add_order',
      args: { table: tableId, items, client: RM.client }
    });
  };

  return { orders, addOrder };
}