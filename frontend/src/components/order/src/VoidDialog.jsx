import { useEffect, useState } from "react";
import { X, Loader2, Ban } from "lucide-react";
import OrderAPI from "../api";

let reasonsCache = null;

/**
 * VoidDialog — asks why items already sent to the kitchen are voided.
 * The server logs the reason (Ren Void Log).
 *
 * Props:
 *   title     what is being voided ("Void 2× Burger", "Void order 00012")
 *   detail    optional line under the title
 *   onConfirm ({ reason, note })
 *   onClose
 */
export function VoidDialog({ title, detail, onConfirm, onClose }) {
  const [reasons, setReasons] = useState(reasonsCache);
  const [reason, setReason] = useState(null);
  const [note, setNote] = useState("");

  useEffect(() => {
    if (reasonsCache) return;
    OrderAPI.getVoidReasons().then((r) => {
      reasonsCache = r || [];
      setReasons(reasonsCache);
    }).catch(() => setReasons([]));
  }, []);

  const current = reasons?.find((r) => r.name === reason);
  const needsNote = !!current?.requires_note;
  const ready = !!reason && (!needsNote || note.trim());

  return (
    <div className="fixed inset-0 z-[1050] flex items-end sm:items-center justify-center bg-black/60 animate-fade-in" onClick={onClose}>
      <div
        className="w-full sm:max-w-md max-h-[90vh] flex flex-col bg-card text-card-foreground border border-border rounded-t-3xl sm:rounded-2xl shadow-2xl animate-slide-up"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="shrink-0 flex items-start gap-3 px-5 pt-4 pb-3 border-b border-border">
          <span className="w-10 h-10 shrink-0 rounded-xl bg-destructive/15 text-destructive flex items-center justify-center">
            <Ban size={20} />
          </span>
          <div className="flex-1 min-w-0">
            <div className="text-base font-semibold leading-tight">{title}</div>
            <div className="text-xs text-muted-foreground mt-0.5">
              {detail || __("Already sent to the kitchen. Choose a reason; it is recorded.")}
            </div>
          </div>
          <button onClick={onClose} className="w-9 h-9 -mr-2 flex items-center justify-center rounded-xl text-muted-foreground hover:bg-muted" aria-label={__("Close")}>
            <X size={20} />
          </button>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto px-5 py-3 space-y-2">
          {!reasons ? (
            <div className="flex justify-center py-6 text-muted-foreground"><Loader2 className="animate-spin" size={20} /></div>
          ) : reasons.length === 0 ? (
            <div className="text-sm text-muted-foreground py-4">{__("No void reasons configured (Ren Void Reason).")}</div>
          ) : (
            reasons.map((r) => (
              <button
                key={r.name}
                onClick={() => setReason(r.name)}
                className={`w-full min-h-[46px] px-4 rounded-xl border text-left text-sm font-medium transition-colors ${
                  reason === r.name ? "border-destructive bg-destructive/10" : "border-border bg-muted/20 hover:bg-muted/50"
                }`}
              >
                {__(r.reason)}
              </button>
            ))
          )}
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={2}
            placeholder={needsNote ? __("Note (required)") : __("Note (optional)")}
            className="w-full mt-1 rounded-xl bg-background border border-border px-3 py-2 text-sm outline-none focus:border-ring resize-none"
          />
        </div>

        <div className="shrink-0 px-5 pt-3 border-t border-border" style={{ paddingBottom: "max(0.75rem, env(safe-area-inset-bottom))" }}>
          <button
            disabled={!ready}
            onClick={() => onConfirm({ reason, note: note.trim() })}
            className="w-full min-h-[48px] rounded-2xl font-semibold text-white bg-destructive disabled:opacity-40"
          >
            {__("Void")}
          </button>
        </div>
      </div>
    </div>
  );
}

export default VoidDialog;
