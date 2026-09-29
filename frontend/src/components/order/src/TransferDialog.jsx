import { useState, useEffect } from "react";
import { Loader2, Utensils, Users } from "lucide-react";
import Modal from "@c/ui/Modal";
import OrderAPI from "../api";

/**
 * TransferDialog — move the current order to another table of the same
 * restaurant. Tables come from api.order.get_transfer_targets.
 *
 * Props: open, onClose, orderName, onConfirm(tableName) => Promise
 */
export function TransferDialog({ open, onClose, orderName, onConfirm }) {
  const [floors, setFloors] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(null);

  useEffect(() => {
    if (!open || !orderName) return;
    let cancelled = false;
    OrderAPI.getTransferTargets(orderName).then(
      (r) => { if (!cancelled) setFloors(r || []); },
      () => { if (!cancelled) setError(__("Could not load the tables")); }
    );
    return () => { cancelled = true; };
  }, [open, orderName]);

  const pick = async (table) => {
    if (table.current || busy) return;
    setBusy(table.name);
    try {
      await onConfirm(table.name);
      onClose?.();
    } finally {
      setBusy(null);
    }
  };

  if (!open) return null;

  return (
    <Modal open={open} onClose={busy ? undefined : onClose} size="lg" title={`${__("Transfer order")} · ${orderName}`}>
      {!floors && !error && (
        <div className="flex justify-center py-16 text-muted-foreground"><Loader2 className="animate-spin" /></div>
      )}
      {error && <p className="p-6 text-sm text-rose-400">{error}</p>}
      {floors && (
        <div className="p-4 space-y-5">
          {floors.map((floor) => (
            <section key={floor.name}>
              <h3 className="text-xs uppercase tracking-wide text-muted-foreground mb-2">{floor.description || floor.name}</h3>
              {floor.rooms.map((room) => (
                <div key={room.name} className="mb-3">
                  <p className="text-sm font-semibold mb-1.5">{room.description || room.name}</p>
                  <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 gap-2">
                    {room.tables.map((t) => (
                      <button
                        key={t.name}
                        onClick={() => pick(t)}
                        disabled={t.current || !!busy}
                        className={`relative rounded-xl border px-2 py-3 text-center transition-colors
                          ${t.current ? "border-blue-500 bg-blue-600/15 cursor-default"
                            : t.orders_count ? "border-amber-500/40 bg-amber-500/10 hover:bg-amber-500/20"
                            : "border-border bg-muted/40 hover:bg-muted"}`}
                      >
                        {busy === t.name && <Loader2 size={14} className="animate-spin absolute top-1.5 right-1.5" />}
                        <span className="block font-bold truncate">{t.description}</span>
                        <span className="flex items-center justify-center gap-2 text-xs text-muted-foreground mt-1">
                          {t.no_of_seats ? <span className="flex items-center gap-0.5"><Users size={12} />{t.no_of_seats}</span> : null}
                          {t.orders_count ? <span className="flex items-center gap-0.5 text-amber-300"><Utensils size={12} />{t.orders_count}</span> : null}
                        </span>
                        {t.current && <span className="block text-[10px] text-blue-300 mt-0.5">{__("Current")}</span>}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </section>
          ))}
        </div>
      )}
    </Modal>
  );
}
