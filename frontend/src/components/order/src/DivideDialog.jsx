import { useState, useMemo } from "react";
import { Minus, Plus, Loader2 } from "lucide-react";
import Modal from "@c/ui/Modal";
import { formatCurrency } from "../orderItems/calculator";

/**
 * DivideDialog — move part of an order's items into a new order on the
 * same table (split the bill). The server recalculates both orders.
 *
 * Props: open, onClose, items (itemsList), onConfirm(map) => Promise
 *   map = { [identifier]: { qty } }
 */
export function DivideDialog({ open, onClose, items = [], onConfirm }) {
  const [moving, setMoving] = useState({});
  const [busy, setBusy] = useState(false);

  const rows = useMemo(() => items.filter((i) => parseFloat(i.qty) > 0), [items]);
  const movedTotal = rows.reduce((acc, i) => acc + (moving[i.identifier] || 0) * (parseFloat(i.rate) || 0), 0);
  const count = Object.values(moving).filter((q) => q > 0).length;

  const change = (item, delta) => {
    setMoving((prev) => {
      const max = parseFloat(item.qty) || 0;
      const next = Math.min(max, Math.max(0, (prev[item.identifier] || 0) + delta));
      return { ...prev, [item.identifier]: next };
    });
  };

  const moveAll = (item) => setMoving((prev) => ({ ...prev, [item.identifier]: parseFloat(item.qty) || 0 }));

  const confirm = async () => {
    const map = Object.fromEntries(
      Object.entries(moving).filter(([, q]) => q > 0).map(([id, qty]) => [id, { qty }])
    );
    if (!Object.keys(map).length) return;
    setBusy(true);
    try {
      await onConfirm(map);
      onClose?.();
    } finally {
      setBusy(false);
    }
  };

  if (!open) return null;

  return (
    <Modal
      open={open}
      onClose={busy ? undefined : onClose}
      size="md"
      title={__("Divide order")}
      footer={(
        <>
          <span className="mr-auto text-sm text-muted-foreground">
            {__("New order")}: <b className="text-card-foreground tabular-nums">{formatCurrency(movedTotal)}</b>
          </span>
          <button onClick={onClose} disabled={busy} className="px-4 py-2 rounded-lg bg-muted hover:bg-muted/70">
            {__("Cancel")}
          </button>
          <button
            onClick={confirm}
            disabled={!count || busy}
            className={`px-5 py-2 rounded-lg font-semibold flex items-center gap-2 ${count && !busy ? "bg-blue-600 hover:bg-blue-500 text-white" : "bg-muted text-muted-foreground"}`}
          >
            {busy && <Loader2 size={16} className="animate-spin" />}
            {__("Move to new order")}
          </button>
        </>
      )}
    >
      <p className="px-5 pt-4 text-sm text-muted-foreground">
        {__("Choose how many of each item go to a new order on this table.")}
      </p>
      <ul className="p-3 space-y-1.5">
        {rows.map((item) => {
          const q = moving[item.identifier] || 0;
          return (
            <li key={item.identifier} className={`flex items-center gap-3 px-3 py-2 rounded-xl border ${q ? "border-blue-500/50 bg-blue-600/10" : "border-border"}`}>
              <button onClick={() => moveAll(item)} className="flex-1 min-w-0 text-left">
                <span className="block truncate font-medium">{item.item_name}</span>
                <span className="text-xs text-muted-foreground tabular-nums">
                  {item.qty} × {formatCurrency(item.rate)}
                </span>
              </button>
              <div className="flex items-center gap-2 shrink-0">
                <button onClick={() => change(item, -1)} disabled={!q} className="h-9 w-9 rounded-lg bg-muted/60 hover:bg-muted flex items-center justify-center disabled:opacity-40">
                  <Minus size={16} />
                </button>
                <span className="w-10 text-center font-bold tabular-nums">{q}</span>
                <button onClick={() => change(item, 1)} disabled={q >= parseFloat(item.qty)} className="h-9 w-9 rounded-lg bg-muted/60 hover:bg-muted flex items-center justify-center disabled:opacity-40">
                  <Plus size={16} />
                </button>
              </div>
            </li>
          );
        })}
      </ul>
    </Modal>
  );
}
