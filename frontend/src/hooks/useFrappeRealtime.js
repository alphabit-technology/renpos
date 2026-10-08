import { useEffect, useRef } from 'react';

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
