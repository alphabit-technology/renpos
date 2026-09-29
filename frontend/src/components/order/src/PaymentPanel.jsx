import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import {
  Loader2, Lock, CheckCircle2, Printer, Banknote, CreditCard,
  Smartphone, Wallet, AlertTriangle, Delete, RotateCw,
} from "lucide-react";
import Modal from "@c/ui/Modal";
import OrderAPI from "../api";
import { createOpeningVoucher } from "@/context/voucher.js";

/**
 * PaymentPanel — charge a Table Order.
 *
 * Totals come from the server (api.order.get_payment_summary), built the
 * same way as the real invoice, so what the cashier sees is what gets
 * invoiced. The server re-validates everything on process_payment.
 *
 * Props:
 *   open, onClose
 *   orderName     Table Order to charge
 *   title         e.g. "R 5 (T-184)"
 *   waitForSync   () => Promise — flushes pending item saves first
 *   onPaid(result) called after a successful payment ("Done" pressed)
 */

const MODE_ICONS = { Cash: Banknote, Bank: CreditCard, Phone: Smartphone };

function round(value, precision = 2) {
  const p = Math.pow(10, precision);
  return Math.round((parseFloat(value) || 0) * p) / p;
}

function money(value, currency) {
  if (typeof window.format_currency === "function") {
    return window.format_currency(value, currency);
  }
  return `${currency || "$"} ${round(value).toFixed(2)}`;
}

/** Suggested cash amounts: next round banknote totals above the due amount. */
function cashSuggestions(due) {
  const out = [];
  for (const step of [1, 5, 10, 20, 50, 100, 500]) {
    const v = Math.ceil(due / step) * step;
    if (v > due && !out.includes(v)) out.push(v);
    if (out.length === 4) break;
  }
  return out;
}

export function PaymentPanel({ open, onClose, orderName, title, waitForSync, onPaid }) {
  const [phase, setPhase] = useState("loading"); // loading | ready | paying | done | error
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);
  const [amounts, setAmounts] = useState({});
  const [activeMode, setActiveMode] = useState(null);
  const [result, setResult] = useState(null);
  const freshInput = useRef(true); // first keypad press replaces the value

  const precision = summary?.precision ?? 2;
  const currency = summary?.currency;
  const due = summary ? round(summary.amount_due, precision) : 0;

  // ── Load summary ─────────────────────────────────
  // The panel is mounted fresh for each payment (keyed by order), so it
  // starts in "loading". State is only set from promise callbacks.
  const fetchSummary = useCallback(async () => {
    await waitForSync?.(); // pending item changes must reach the server first
    return OrderAPI.getPaymentSummary(orderName);
  }, [orderName, waitForSync]);

  const applySummary = useCallback((s) => {
    setSummary(s);
    const modes = s.payment_modes || [];
    const def = modes.find((m) => m.default) || modes[0];
    setActiveMode(def?.mode_of_payment || null);
    setAmounts(def ? { [def.mode_of_payment]: String(round(s.amount_due, s.precision)) } : {});
    freshInput.current = true;
    setPhase("ready");
  }, []);

  const failSummary = useCallback((e) => {
    setError(e?.message || __("Could not load the payment details"));
    setPhase("error");
  }, []);

  useEffect(() => {
    if (!open || !orderName) return;
    let cancelled = false;
    fetchSummary().then(
      (s) => { if (!cancelled) applySummary(s); },
      (e) => { if (!cancelled) failSummary(e); }
    );
    return () => { cancelled = true; };
  }, [open, orderName, fetchSummary, applySummary, failSummary]);

  const retry = () => {
    setPhase("loading");
    setError(null);
    fetchSummary().then(applySummary, failSummary);
  };

  // ── Derived amounts ──────────────────────────────
  const modeType = useCallback(
    (mode) => summary?.payment_modes?.find((m) => m.mode_of_payment === mode)?.type,
    [summary]
  );

  const { paid, nonCashPaid } = useMemo(() => {
    let paid = 0, cashPaid = 0;
    for (const [mode, v] of Object.entries(amounts)) {
      const n = parseFloat(v) || 0;
      paid += n;
      if (modeType(mode) === "Cash") cashPaid += n;
    }
    paid = round(paid, precision);
    return { paid, nonCashPaid: round(paid - cashPaid, precision) };
  }, [amounts, modeType, precision]);

  const remaining = round(Math.max(due - paid, 0), precision);
  const change = round(Math.max(paid - due, 0), precision);
  const nonCashTooHigh = nonCashPaid > due;
  const canCharge = phase === "ready" && !summary?.register?.problem
    && paid >= due && !nonCashTooHigh && paid > 0;

  // ── Editing ──────────────────────────────────────
  const selectMode = (mode) => {
    setActiveMode(mode);
    freshInput.current = true;
    setAmounts((prev) => {
      if (parseFloat(prev[mode]) > 0) return prev;
      const others = Object.entries(prev)
        .filter(([m]) => m !== mode)
        .reduce((a, [, v]) => a + (parseFloat(v) || 0), 0);
      const rest = round(Math.max(due - others, 0), precision);
      return { ...prev, [mode]: rest ? String(rest) : "" };
    });
  };

  const setActiveAmount = (value) => {
    if (!activeMode) return;
    setAmounts((prev) => ({ ...prev, [activeMode]: value }));
  };

  const pressKey = (key) => {
    if (!activeMode) return;
    const current = freshInput.current ? "" : (amounts[activeMode] || "");
    freshInput.current = false;
    let next;
    if (key === "back") next = current.slice(0, -1);
    else if (key === "clear") next = "";
    else if (key === ".") next = current.includes(".") ? current : (current || "0") + ".";
    else next = current === "0" ? key : current + key;
    setActiveAmount(next);
  };

  // ── Charge ───────────────────────────────────────
  const charge = useCallback(async () => {
    if (!canCharge) return;
    setPhase("paying");
    setError(null);
    try {
      await waitForSync?.();
      const payments = Object.entries(amounts)
        .map(([mode_of_payment, v]) => ({ mode_of_payment, amount: round(v, precision) }))
        .filter((p) => p.amount > 0);
      const res = await OrderAPI.processPayment(orderName, payments);
      setResult(res);
      setPhase("done");
    } catch (e) {
      // Frappe already shows the server message in a dialog
      setError(e?.message || __("The payment was not completed"));
      setPhase("ready");
    }
  }, [canCharge, amounts, orderName, precision, waitForSync]);

  const openRegister = async () => {
    const ok = await createOpeningVoucher();
    if (ok) retry();
  };

  const printInvoice = () => {
    if (!result?.invoice) return;
    const doctype = result.invoice_doctype || summary?.invoice_doctype || "POS Invoice";
    const url = `/printview?doctype=${encodeURIComponent(doctype)}&name=${encodeURIComponent(result.invoice)}&trigger_print=1`;
    window.open(url, "_blank");
  };

  const finish = () => {
    onPaid?.(result);
    onClose?.();
  };

  // Keyboard: Enter charges / finishes, Esc closes only this panel,
  // digits go to the keypad. Capture phase so the order manager
  // underneath doesn't also react.
  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      const typing = e.target?.tagName === "INPUT";
      if (e.key === "Escape") {
        e.stopImmediatePropagation();
        if (phase === "done") finish();
        else if (phase !== "paying") onClose?.();
      } else if (e.key === "Enter") {
        e.stopImmediatePropagation();
        e.preventDefault();
        if (phase === "done") finish();
        else charge();
      } else if (!typing && phase === "ready" && /^[0-9.]$/.test(e.key)) {
        pressKey(e.key);
      } else if (!typing && phase === "ready" && e.key === "Backspace") {
        pressKey("back");
      }
    };
    window.addEventListener("keydown", handler, true);
    return () => window.removeEventListener("keydown", handler, true);
  });

  if (!open) return null;

  // ═════════════════════════════════════════════════
  // RENDER
  // ═════════════════════════════════════════════════

  const header = (
    <div className="flex items-baseline gap-2 min-w-0">
      <span className="truncate">{__("Payment")}</span>
      <span className="text-sm font-normal text-muted-foreground truncate">
        {title} · {orderName}
      </span>
    </div>
  );

  let body;

  if (phase === "loading") {
    body = (
      <div className="flex flex-col items-center justify-center gap-3 py-24 text-muted-foreground">
        <Loader2 size={28} className="animate-spin" />
        <span className="text-sm">{__("Calculating totals…")}</span>
      </div>
    );
  } else if (phase === "error") {
    body = (
      <div className="flex flex-col items-center justify-center gap-4 py-20 px-6 text-center">
        <AlertTriangle size={32} className="text-amber-400" />
        <p className="text-sm text-card-foreground max-w-sm">{error}</p>
        <button onClick={retry} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-muted hover:bg-muted/70 text-sm">
          <RotateCw size={16} /> {__("Try again")}
        </button>
      </div>
    );
  } else if (phase === "done") {
    body = (
      <div className="flex flex-col items-center justify-center gap-5 py-14 px-6 text-center">
        <CheckCircle2 size={56} className="text-emerald-400" />
        <div>
          <p className="text-lg font-semibold text-card-foreground">{__("Payment complete")}</p>
          <p className="text-sm text-muted-foreground mt-1">
            {result?.invoice_doctype} <span className="font-mono">{result?.invoice}</span>
          </p>
        </div>
        {result?.change_amount > 0 && (
          <div className="rounded-xl bg-emerald-500/10 border border-emerald-500/40 px-8 py-4">
            <p className="text-xs uppercase tracking-wide text-emerald-300">{__("Change")}</p>
            <p className="text-4xl font-extrabold text-emerald-300 tabular-nums">
              {money(result.change_amount, result.currency || currency)}
            </p>
          </div>
        )}
        <div className="flex gap-3 mt-2">
          <button onClick={printInvoice} className="flex items-center gap-2 px-5 py-3 rounded-xl bg-muted hover:bg-muted/70 font-semibold">
            <Printer size={18} /> {__("Print")}
          </button>
          <button onClick={finish} className="px-8 py-3 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold">
            {__("Done")}
          </button>
        </div>
      </div>
    );
  } else {
    const register = summary?.register || {};
    const paying = phase === "paying";

    body = (
      <div className="flex flex-col md:flex-row min-h-0">
        {/* ── Left: totals ── */}
        <section className="md:w-[42%] shrink-0 p-5 border-b md:border-b-0 md:border-r border-border flex flex-col gap-4">
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">{__("Customer")}</p>
            <p className="font-semibold text-card-foreground truncate">{summary?.customer_name}</p>
          </div>

          <dl className="text-sm space-y-1.5">
            <Row label={`${__("Net total")} (${summary?.items_count} ${__("items")})`} value={money(summary?.net_total, currency)} />
            {(summary?.taxes || []).map((t, i) => (
              <Row key={i} label={t.description} value={money(t.amount, currency)} muted />
            ))}
            {summary?.discount_amount > 0 && (
              <Row label={__("Discount")} value={`- ${money(summary.discount_amount, currency)}`} muted />
            )}
            {Math.abs(summary?.rounding_adjustment || 0) > 0 && (
              <Row label={__("Rounding")} value={money(summary.rounding_adjustment, currency)} muted />
            )}
          </dl>

          <div className="rounded-xl bg-blue-600/10 border border-blue-500/30 p-4">
            <p className="text-xs uppercase tracking-wide text-blue-300">{__("Total to pay")}</p>
            <p className="text-4xl font-extrabold text-card-foreground tabular-nums">{money(due, currency)}</p>
          </div>

          <dl className="text-sm space-y-1.5 mt-auto">
            <Row label={__("Paid")} value={money(paid, currency)} />
            {remaining > 0 ? (
              <Row label={__("Remaining")} value={money(remaining, currency)} className="text-rose-400 font-semibold" />
            ) : (
              <Row label={__("Change")} value={money(change, currency)} className="text-emerald-400 font-semibold text-base" />
            )}
          </dl>
          {nonCashTooHigh && (
            <p className="text-xs text-amber-400">
              {__("Card/transfer payments can't exceed the total; only cash can be overpaid.")}
            </p>
          )}
        </section>

        {/* ── Right: payment entry ── */}
        <section className="flex-1 p-5 flex flex-col gap-4 min-w-0">
          {register.problem ? (
            <div className="flex-1 flex flex-col items-center justify-center gap-4 text-center py-10">
              <Lock size={36} className="text-amber-400" />
              {register.problem === "no_permission" ? (
                <>
                  <p className="font-semibold text-card-foreground">{__("Your user can't take payments")}</p>
                  <p className="text-sm text-muted-foreground max-w-xs">
                    {__("You can show this bill to the customer; a cashier has to charge it. Cashiers need the Accounts User and Sales Manager roles (or equivalent permissions).")}
                  </p>
                </>
              ) : register.problem === "closed" ? (
                <>
                  <p className="font-semibold text-card-foreground">{__("Your cash register is closed")}</p>
                  <p className="text-sm text-muted-foreground max-w-xs">
                    {__("Open your register (POS Opening Entry) for {0} to take payments.", [register.pos_profile])}
                  </p>
                  <button onClick={openRegister} className="px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold">
                    {__("Open register")}
                  </button>
                </>
              ) : (
                <>
                  <p className="font-semibold text-card-foreground">{__("Your register shift is from a previous day")}</p>
                  <p className="text-sm text-muted-foreground max-w-xs">
                    {__("Close shift {0} (POS Closing Entry) and open a new one.", [register.opening_entry])}
                  </p>
                  <a href="/app/pos-closing-entry/new" target="_blank" rel="noreferrer"
                     className="px-5 py-2.5 rounded-xl bg-muted hover:bg-muted/70 font-semibold">
                    {__("Close register")}
                  </a>
                </>
              )}
            </div>
          ) : (
            <>
              {/* Modes */}
              <div className="grid grid-cols-2 gap-2">
                {(summary?.payment_modes || []).map((m) => {
                  const Icon = MODE_ICONS[m.type] || Wallet;
                  const active = m.mode_of_payment === activeMode;
                  const value = parseFloat(amounts[m.mode_of_payment]) || 0;
                  return (
                    <button
                      key={m.mode_of_payment}
                      onClick={() => selectMode(m.mode_of_payment)}
                      disabled={paying}
                      className={`flex items-center justify-between gap-2 px-3 py-3 rounded-xl border text-left transition-colors
                        ${active ? "border-blue-500 bg-blue-600/15" : "border-border bg-muted/40 hover:bg-muted"}`}
                    >
                      <span className="flex items-center gap-2 min-w-0">
                        <Icon size={18} className={active ? "text-blue-300" : "text-muted-foreground"} />
                        <span className="truncate font-medium">{m.mode_of_payment}</span>
                      </span>
                      {value > 0 && (
                        <span className="text-sm font-semibold tabular-nums">{money(value, currency)}</span>
                      )}
                    </button>
                  );
                })}
              </div>

              {/* Amount for the active mode */}
              {activeMode && (
                <div className="flex flex-col gap-2">
                  <label className="text-xs uppercase tracking-wide text-muted-foreground">
                    {__("Amount")} · {activeMode}
                  </label>
                  <input
                    inputMode="decimal"
                    value={amounts[activeMode] ?? ""}
                    onChange={(e) => { freshInput.current = false; setActiveAmount(e.target.value.replace(/[^0-9.]/g, "")); }}
                    onFocus={(e) => e.target.select()}
                    disabled={paying}
                    className="w-full rounded-xl bg-background border border-border px-4 py-3 text-3xl font-bold tabular-nums text-right outline-none focus:border-blue-500"
                  />
                  <div className="flex flex-wrap gap-2">
                    <Quick onClick={() => { freshInput.current = true; selectModeAmount(setAmounts, activeMode, amounts, due, precision); }}>
                      {__("Exact")}
                    </Quick>
                    {modeType(activeMode) === "Cash" && cashSuggestions(remaining + (parseFloat(amounts[activeMode]) || 0)).map((v) => (
                      <Quick key={v} onClick={() => { freshInput.current = true; setActiveAmount(String(v)); }}>
                        {money(v, currency)}
                      </Quick>
                    ))}
                  </div>
                </div>
              )}

              {/* Keypad */}
              <div className="grid grid-cols-3 gap-2">
                {["7", "8", "9", "4", "5", "6", "1", "2", "3", ".", "0", "back"].map((k) => (
                  <button
                    key={k}
                    onClick={() => pressKey(k)}
                    disabled={paying || !activeMode}
                    className="h-12 rounded-xl bg-muted/60 hover:bg-muted text-xl font-semibold flex items-center justify-center"
                  >
                    {k === "back" ? <Delete size={20} /> : k}
                  </button>
                ))}
              </div>

              {error && <p className="text-sm text-rose-400">{error}</p>}

              <button
                onClick={charge}
                disabled={!canCharge || paying}
                className={`mt-auto w-full flex items-center justify-center gap-2 py-4 rounded-xl text-lg font-extrabold transition-colors
                  ${canCharge && !paying
                    ? "bg-blue-600 hover:bg-blue-500 active:bg-blue-700 text-white"
                    : "bg-muted text-muted-foreground cursor-not-allowed"}`}
              >
                {paying
                  ? <><Loader2 size={20} className="animate-spin" /> {__("Charging…")}</>
                  : `${__("Charge")} ${money(due, currency)}`}
              </button>
            </>
          )}
        </section>
      </div>
    );
  }

  return (
    <Modal
      open={open}
      onClose={phase === "done" ? finish : onClose}
      title={header}
      size="lg"
      closeOnEsc={false}
      closeOnOverlay={phase !== "paying"}
      showClose={phase !== "paying"}
    >
      {body}
    </Modal>
  );
}

/** "Exact": the active mode pays whatever the other modes don't. */
function selectModeAmount(setAmounts, mode, amounts, due, precision) {
  const others = Object.entries(amounts)
    .filter(([m]) => m !== mode)
    .reduce((a, [, v]) => a + (parseFloat(v) || 0), 0);
  const rest = round(Math.max(due - others, 0), precision);
  setAmounts({ ...amounts, [mode]: String(rest) });
}

function Row({ label, value, muted = false, className = "" }) {
  return (
    <div className={`flex justify-between gap-3 ${muted ? "text-muted-foreground" : "text-card-foreground"} ${className}`}>
      <dt className="truncate">{label}</dt>
      <dd className="tabular-nums shrink-0">{value}</dd>
    </div>
  );
}

function Quick({ children, onClick }) {
  return (
    <button onClick={onClick} className="px-3 py-2 rounded-lg bg-muted/60 hover:bg-muted text-sm font-semibold tabular-nums">
      {children}
    </button>
  );
}
