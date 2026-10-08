import { useEffect } from "react";

/**
 * Guests' own orders (online pickup, QR at the table: api/online.py) pop up
 * on every screen of the restaurant with a chime: the pickup order that went
 * straight to the kitchen, or the table's order waiting for its server to
 * review and send it.
 */

function chime() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    [880, 1320].forEach((f, i) => {
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.frequency.value = f;
      g.gain.setValueAtTime(0.0001, ctx.currentTime + i * 0.18);
      g.gain.exponentialRampToValueAtTime(0.15, ctx.currentTime + i * 0.18 + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + i * 0.18 + 0.35);
      o.connect(g).connect(ctx.destination);
      o.start(ctx.currentTime + i * 0.18);
      o.stop(ctx.currentTime + i * 0.18 + 0.4);
    });
    setTimeout(() => ctx.close(), 1200);
  } catch { /* no audio */ }
}

export default function GuestOrderAlerts() {
  useEffect(() => {
    const handler = (msg) => {
      const mine = window.REN?.restaurant?.name;
      if (!msg || (mine && msg.restaurant && msg.restaurant !== mine)) return;
      const who = msg.guest ? ` · ${msg.guest}` : "";
      let text;
      if (msg.mode === "pickup") {
        const at = msg.pickup_time ? new Date(String(msg.pickup_time).replace(" ", "T"))
          .toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "";
        text = msg.held
          ? __("Online pickup order for {0}{1} (scheduled)", [at, who])
          : __("Online pickup order{0}: sent to the kitchen, pickup {1}", [who, at]);
      } else {
        text = msg.sent
          ? __("Table {0} ordered from their phone{1}: sent to the kitchen", [msg.table_name, who])
          : __("Table {0} ordered from their phone{1}: review and send it", [msg.table_name, who]);
      }
      frappe.show_alert({ message: text, indicator: msg.sent ? "green" : "orange" }, 12);
      chime();
    };
    frappe.realtime.on("ren_guest_order", handler);
    return () => frappe.realtime.off("ren_guest_order", handler);
  }, []);
  return null;
}
