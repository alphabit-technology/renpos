import { useEffect, useRef, useCallback } from 'react';

export function useFrappeRealtime(event, callback, deps = []) {
  const callbackRef = useRef(callback);

  // Siempre mantener la referencia actualizada
  useEffect(() => {
    callbackRef.current = callback;
  });

  useEffect(() => {
    const handler = (...args) => callbackRef.current(...args);

    frappe.realtime.on(event, handler);

    return () => {
      frappe.realtime.off(event, handler);
    };
  }, [event, ...deps]);
}

export function useRealtimeEmit() {
  return useCallback((method, args = {}) => {
    return frappe.call({
      method: `restaurant_management.api.${method}`,
      args
    });
  }, []);
}