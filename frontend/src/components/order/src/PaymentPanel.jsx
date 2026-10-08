import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import {
  Loader2, Lock, CheckCircle2, Printer, Banknote, CreditCard,
  Smartphone, Wallet, AlertTriangle, Delete, RotateCw, Users2, Minus, Plus, HandCoins, Gift, Check,
} from "lucide-react";
import Modal from "@c/ui/Modal";
import OrderAPI from "../api";
import { RegisterPanel } from "@c/register/RegisterPanel.jsx";

/**
 * PaymentPanel — charge a Ren Order.
 *
 * Totals come from the server (api.order.get_payment_summary), built the
 * same way as the real invoice, so what the cashier sees is what gets
 * invoiced. The server re-validates everything on process_payment.
 *
 * Props:
 *   open, onClose
 *   orderName     Ren Order to charge
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
  const [tip, setTip] = useState(0);           // amount added on top of the bill
  const [tipChoice, setTipChoice] = useState("none"); // "none" | percentage | "custom"
  const [splitN, setSplitN] = useState(1);     // split the check evenly between N guests
  const [parts, setParts] = useState([]);      // [{mode, amount}] guests already charged
  // Stripe Terminal: approved card charges and the one waiting on the reader
  const [cardPayments, setCardPayments] = useState([]); // [{name, amount, mode_of_payment, card}]
  const [cardPending, setCardPending] = useState(null); // {name, amount, mode_of_payment, reader, label, share}
  const [cardError, setCardError] = useState(null);
  const [readerId, setReaderId] = useState(null);
  // loyalty points used as part of the payment
  const [points, setPoints] = useState(0);
  // amount due with the tip and the points, as ERPNext computes it (rounding applies to bill + tip)
  const [tipDue, setTipDue] = useState(null);
  const [tipLoading, setTipLoading] = useState(false);

  const precision = summary?.precision ?? 2;
  const currency = summary?.currency;
  const billDue = summary ? round(summary.amount_due, precision) : 0;
  const loyalty = summary?.loyalty;
  const pointsValue = round(points * (loyalty?.point_value || 0), precision);
  const due = tip || points ? round(tipDue ?? billDue + tip - pointsValue, precision) : billDue;
  const tips = summary?.tips;

  // Evenly split shares; the last guest absorbs the rounding cents.
  const shares = useMemo(() => {
    if (splitN <= 1) return [];
    const each = Math.floor((due / splitN) * 100) / 100;
    return Array.from({ length: splitN }, (_, i) =>
      i === splitN - 1 ? round(due - each * (splitN - 1), precision) : each);
  }, [due, splitN, precision]);

  const resetAmounts = (total, mode = activeMode) => {
    setParts([]);
    freshInput.current = true;
    setAmounts(mode ? { [mode]: String(round(total, precision)) } : {});
  };

  // the server recomputes the total with the tip and the points used
  const recalc = (nextTip, nextPoints, onFail) => {
    setTipDue(null);
    if (splitN > 1) { setParts([]); setAmounts({}); }
    else resetAmounts(Math.max(billDue + nextTip - nextPoints * (loyalty?.point_value || 0), 0));
    if (!nextTip && !nextPoints) {
      if (summary?.loyalty) OrderAPI.getPaymentSummary(orderName).then((s) => s.loyalty && setSummary((prev) => ({ ...prev, loyalty: { ...prev.loyalty, earns: s.loyalty.earns } })));
      return;
    }
    setTipLoading(true);
    OrderAPI.getPaymentSummary(orderName, nextTip, nextPoints).then(
      (s) => {
        const d = round(s.amount_due, precision);
        setTipDue(d);
        if (splitN <= 1) resetAmounts(d);
        // points this bill earns change with the tip and the points used
        if (s.loyalty) setSummary((prev) => (prev?.loyalty ? { ...prev, loyalty: { ...prev.loyalty, earns: s.loyalty.earns } } : prev));
      },
      () => { onFail?.(); resetAmounts(billDue); }
    ).finally(() => setTipLoading(false));
  };

  const chooseTip = (choice, customValue) => {
    let value = 0;
    if (choice === "custom") value = round(parseFloat(customValue) || 0, precision);
    else if (choice !== "none") value = round((tips?.base || 0) * choice / 100, precision);
    setTipChoice(choice);
    setTip(value);
    recalc(value, points, () => { setTipChoice("none"); setTip(0); setPoints(0); });
  };

  const applyPoints = (n) => {
    const next = Math.max(0, Math.min(parseInt(n, 10) || 0, loyalty?.max_points || 0));
    setPoints(next);
    recalc(tip, next, () => { setPoints(0); setTip(0); setTipChoice("none"); });
  };

  const changeSplit = (n) => {
    const next = Math.max(1, Math.min(20, n));
    setSplitN(next);
    if (next > 1) { setParts([]); setAmounts({}); }
    else resetAmounts(due);
  };

  // charge the next guest's share to the active mode
  const payNextShare = () => {
    if (!activeMode || parts.length >= shares.length) return;
    const amount = shares[parts.length];
    if (readersFor(activeMode).length) {
      startCard(amount, true);
      return;
    }
    setParts((p) => [...p, { mode: activeMode, amount }]);
    setAmounts((prev) => ({
      ...prev,
      [activeMode]: String(round((parseFloat(prev[activeMode]) || 0) + amount, precision)),
    }));
  };

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
    setTip(0);
    setTipChoice("none");
    setTipDue(null);
    setPoints(0);
    setSplitN(1);
    setParts([]);
    const cards = s.card_payments || [];
    const approved = cards.filter((c) => c.status === "Succeeded");
    setCardPayments(approved.map((c) => ({ name: c.name, amount: c.amount, mode_of_payment: c.mode_of_payment, card: c.card })));
    const pending = cards.find((c) => c.status === "Pending");
    if (pending) {
      const r = (s.card_readers || []).find((x) => x.reader === pending.reader);
      setCardPending({ ...pending, label: r?.label || pending.reader, share: false });
    }
    if (approved.length) {
      // what the cards already paid is not asked again
      const def2 = (s.payment_modes || []).find((m) => m.default) || (s.payment_modes || [])[0];
      const rest = round(s.amount_due - approved.reduce((a, c) => a + c.amount, 0), s.precision);
      setAmounts(def2 && rest > 0 ? { [def2.mode_of_payment]: String(rest) } : {});
    }
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

  // ── Card readers (Stripe Terminal) ────────────────
  const readersFor = (mode) => (summary?.card_readers || []).filter((r) => r.mode_of_payment === mode);
  const activeReaders = activeMode ? readersFor(activeMode) : [];
  const activeReader = activeReaders.find((r) => r.reader === readerId) || activeReaders[0];
  const cardTotal = round(cardPayments.reduce((a, c) => a + c.amount, 0), precision);

  // For a reader mode the amount box is "what to charge next on the card";
  // only approved card charges count as paid.
  let paidRaw = 0, cashPaid = 0;
  for (const [mode, v] of Object.entries(amounts)) {
    if (readersFor(mode).length) continue;
    const n = parseFloat(v) || 0;
    paidRaw += n;
    if (modeType(mode) === "Cash") cashPaid += n;
  }
  const paid = round(paidRaw + cardTotal, precision);
  const nonCashPaid = round(paid - cashPaid, precision);

  const remaining = round(Math.max(due - paid, 0), precision);
  const change = round(Math.max(paid - due, 0), precision);
  const nonCashTooHigh = nonCashPaid > due;
  const canCharge = phase === "ready" && !summary?.register?.problem && !tipLoading && !cardPending
    && paid >= due && !nonCashTooHigh && (paid > 0 || (points > 0 && due <= 0));

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
  const charge = async () => {
    if (!canCharge) return;
    setPhase("paying");
    setError(null);
    try {
      await waitForSync?.();
      const payments = Object.entries(amounts)
        .filter(([mode]) => !readersFor(mode).length)
        .map(([mode_of_payment, v]) => ({ mode_of_payment, amount: round(v, precision) }))
        .filter((p) => p.amount > 0)
        .concat(cardPayments.map((c) => ({ mode_of_payment: c.mode_of_payment, amount: c.amount, card_payment: c.name })));
      const res = await OrderAPI.processPayment(orderName, payments, tip, points);
      setResult(res);
      setPhase("done");
    } catch (e) {
      // Frappe already shows the server message in a dialog
      setError(e?.message || __("The payment was not completed"));
      setPhase("ready");
    }
  };

  // ── Card on the reader ──────────────────────────
  const startCard = async (amount, share = false) => {
    const reader = activeReader;
    amount = round(amount, precision);
    if (!reader || amount <= 0 || cardPending || tipLoading) return;
    setCardError(null);
    try {
      await waitForSync?.();
      const cp = await OrderAPI.startCardPayment(orderName, reader.reader, amount);
      setCardPending({ ...cp, reader: reader.reader, label: reader.label, share });
    } catch {
      setCardError(__("The reader could not start the payment"));
    }
  };

  const cancelCard = async () => {
    if (!cardPending) return;
    try {
      const st = await OrderAPI.cancelCardPayment(cardPending.name);
      if (st.status === "Succeeded") cardApproved(st);
      else if (st.status === "Failed" || st.status === "Canceled") setCardPending(null);
      // still Pending: the customer is paying, polling goes on
    } catch { /* keep polling */ }
  };

  const cardApproved = (st) => {
    const pending = cardPending;
    setCardPending(null);
    setCardPayments((list) => [...list, { name: st.name, amount: st.amount, mode_of_payment: st.mode_of_payment, card: st.card }]);
    if (pending?.share) setParts((p) => [...p, { mode: st.mode_of_payment, amount: st.amount }]);
    // next amount to charge on the card: whatever is still missing
    setAmounts((prev) => ({ ...prev, [st.mode_of_payment]: "" }));
  };

  // poll the reader while a card payment is pending
  useEffect(() => {
    if (!cardPending) return;
    let stop = false;
    const tick = async () => {
      if (stop) return;
      try {
        const st = await OrderAPI.cardPaymentStatus(cardPending.name);
        if (stop) return;
        if (st.status === "Succeeded") return cardApproved(st);
        if (st.status === "Failed" || st.status === "Canceled") {
          setCardPending(null);
          setCardError(st.failure_message || __("The card payment was not completed"));
          return;
        }
      } catch { /* network hiccup: keep polling */ }
      timer = setTimeout(tick, 1500);
    };
    let timer = setTimeout(tick, 1200);
    return () => { stop = true; clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cardPending?.name]);

  // everything paid by card: finish without an extra tap
  const autoCharge = useRef(false);
  useEffect(() => {
    if (cardPayments.length && canCharge && !autoCharge.current && Object.entries(amounts)
      .every(([mode, v]) => readersFor(mode).length || !(parseFloat(v) > 0))) {
      autoCharge.current = true;
      charge();
    }
  });

  const [registerOpen, setRegisterOpen] = useState(false);
  const openRegister = () => setRegisterOpen(true);

  const printInvoice = () => {
    if (!result?.invoice) return;
    const doctype = result.invoice_doctype || summary?.invoice_doctype || "POS Invoice";
    if (summary?.receipt_printer) {
      OrderAPI.printReceipt(doctype, result.invoice).then(
        () => frappe.show_alert({ message: __("Receipt sent to {0}", [summary.receipt_printer]), indicator: "green" }),
        () => {}
      );
      return;
    }
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
        {result?.print_job && (
          <p className="text-xs text-muted-foreground">{__("Receipt sent to {0}", [summary?.receipt_printer])}</p>
        )}
        {(result?.loyalty_amount > 0 || result?.points_earned > 0) && (
          <p className="text-sm text-muted-foreground">
            {result.loyalty_amount > 0 && <>{__("Paid with points")} <span className="font-semibold text-card-foreground">{money(result.loyalty_amount, result.currency || currency)}</span>{result.points_earned > 0 ? " · " : ""}</>}
            {result.points_earned > 0 && <>{__("Earned {0} points", [result.points_earned])}</>}
          </p>
        )}
        {result?.tip > 0 && (
          <p className="text-sm text-muted-foreground">{__("Tip")} <span className="font-semibold text-card-foreground">{money(result.tip, result.currency || currency)}</span></p>
        )}
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
      <div className="flex flex-col md:flex-row min-h-0 md:max-h-[calc(85vh-64px)]">
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

          {tips?.enabled && !summary?.register?.problem && (
            <div>
              <p className="text-xs uppercase tracking-wide text-muted-foreground mb-1.5 flex items-center gap-1.5">
                <HandCoins size={13} /> {__("Tip")}
              </p>
              <div className="flex flex-wrap gap-1.5">
                <TipChip active={tipChoice === "none"} disabled={phase === "paying"} onClick={() => chooseTip("none")}>{__("No tip")}</TipChip>
                {(tips.percentages || []).map((p) => (
                  <TipChip key={p} active={tipChoice === p} disabled={phase === "paying"} onClick={() => chooseTip(p)}>
                    <span className="block leading-tight">{p}%</span>
                    <span className="block text-[11px] opacity-75 tabular-nums">{money((tips.base || 0) * p / 100, currency)}</span>
                  </TipChip>
                ))}
                <NumberChip
                  active={tipChoice === "custom"} disabled={phase === "paying"}
                  label={tipChoice === "custom" ? money(tip, currency) : __("Custom")}
                  initial={tipChoice === "custom" ? tip : ""} placeholder={__("Tip")}
                  onApply={(v) => chooseTip("custom", v)}
                />
              </div>
            </div>
          )}

          {!loyalty && summary?.loyalty_join && !summary?.register?.problem && (
            <button
              onClick={async () => {
                try {
                  await OrderAPI.joinLoyalty(orderName);
                  const s = await OrderAPI.getPaymentSummary(orderName, tip, 0);
                  setSummary((prev) => ({ ...prev, loyalty: s.loyalty, loyalty_join: null }));
                } catch { /* shown by Frappe */ }
              }}
              disabled={phase === "paying"}
              className="self-start flex items-center gap-1.5 text-xs font-semibold px-3 py-2 rounded-lg border border-border text-muted-foreground hover:text-foreground hover:bg-muted/50"
            >
              <Gift size={13} /> {__("Join {0}", [summary.loyalty_join])}
            </button>
          )}

          {loyalty && !summary?.register?.problem && (
            <div>
              <p className="text-xs uppercase tracking-wide text-muted-foreground mb-1.5 flex items-center gap-1.5">
                <Gift size={13} /> {__("Loyalty")}{loyalty.tier ? ` · ${loyalty.tier}` : ""}
                <span className="normal-case tracking-normal ml-auto tabular-nums">
                  {__("{0} points", [loyalty.points])} · {money(loyalty.value, currency)}
                </span>
              </p>
              {loyalty.max_points > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  <TipChip active={!points} disabled={phase === "paying"} onClick={() => applyPoints(0)}>{__("Keep points")}</TipChip>
                  <TipChip active={points > 0 && points === loyalty.max_points} disabled={phase === "paying"} onClick={() => applyPoints(loyalty.max_points)}>
                    <span className="block leading-tight">{__("Use {0}", [loyalty.max_points])}</span>
                    <span className="block text-[11px] opacity-75 tabular-nums">{money(loyalty.max_points * loyalty.point_value, currency)}</span>
                  </TipChip>
                  <NumberChip
                    integer max={loyalty.max_points}
                    active={points > 0 && points !== loyalty.max_points} disabled={phase === "paying"}
                    label={points > 0 && points !== loyalty.max_points ? __("{0} points", [points]) : __("Other")}
                    initial={points > 0 && points !== loyalty.max_points ? points : ""}
                    placeholder={__("Up to {0}", [loyalty.max_points])}
                    onApply={(v) => applyPoints(v)}
                  />
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">{__("No points to use yet")}</p>
              )}
              {loyalty.earns > 0 && (
                <p className="text-[11px] text-muted-foreground mt-1">{__("This bill earns {0} points", [loyalty.earns])}</p>
              )}
            </div>
          )}

          <div className="rounded-xl bg-blue-600/10 border border-blue-500/30 p-4">
            {(tip > 0 || points > 0) && (
              <p className="text-xs text-muted-foreground tabular-nums">
                {__("Bill")} {money(billDue, currency)}
                {tip > 0 && <> + {__("Tip")} {money(tip, currency)}</>}
                {points > 0 && <> − {__("Points")} {money(pointsValue, currency)}</>}
              </p>
            )}
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
        <section className="flex-1 p-5 pb-0 flex flex-col gap-3 min-w-0 md:overflow-y-auto">
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
                  <button onClick={openRegister}
                     className="px-5 py-2.5 rounded-xl bg-muted hover:bg-muted/70 font-semibold">
                    {__("Close register")}
                  </button>
                </>
              )}
            </div>
          ) : (
            <>
              {/* Split evenly */}
              <div className="flex items-center gap-2 text-sm">
                <Users2 size={16} className="text-muted-foreground" />
                <span className="text-muted-foreground">{__("Split evenly")}</span>
                <div className="ml-auto flex items-center gap-1">
                  <button onClick={() => changeSplit(splitN - 1)} disabled={paying || splitN <= 1}
                          className="w-9 h-9 rounded-lg bg-muted/60 hover:bg-muted flex items-center justify-center disabled:opacity-30" aria-label={__("Fewer guests")}>
                    <Minus size={16} />
                  </button>
                  <span className="w-8 text-center font-semibold tabular-nums">{splitN}</span>
                  <button onClick={() => changeSplit(splitN + 1)} disabled={paying}
                          className="w-9 h-9 rounded-lg bg-muted/60 hover:bg-muted flex items-center justify-center" aria-label={__("More guests")}>
                    <Plus size={16} />
                  </button>
                </div>
              </div>
              {splitN > 1 && (
                <div className="rounded-xl border border-border bg-muted/20 p-3 space-y-2">
                  <div className="flex flex-wrap gap-1.5">
                    {shares.map((amount, i) => {
                      const part = parts[i];
                      return (
                        <span key={i} className={`px-2.5 py-1 rounded-lg text-xs tabular-nums border ${
                          part ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-300" : i === parts.length ? "border-blue-500 bg-blue-600/15" : "border-border"
                        }`}>
                          {__("Guest {0}", [i + 1])} · {money(amount, currency)}{part ? ` · ${part.mode}` : ""}
                        </span>
                      );
                    })}
                  </div>
                  {parts.length < shares.length ? (
                    <button onClick={payNextShare} disabled={paying || !activeMode}
                            className="w-full py-2.5 rounded-lg bg-blue-600/80 hover:bg-blue-600 text-white text-sm font-semibold">
                      {__("Guest {0} pays {1} with {2}", [parts.length + 1, money(shares[parts.length], currency), activeMode || "…"])}
                    </button>
                  ) : (
                    <p className="text-xs text-emerald-300">{__("All guests paid. Charge to finish.")}</p>
                  )}
                  {parts.length > 0 && (
                    <button onClick={() => { setParts([]); setAmounts({}); }} disabled={paying}
                            className="text-xs text-muted-foreground underline">{__("Start over")}</button>
                  )}
                </div>
              )}

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

              {/* Card reader for the active mode */}
              {activeMode && activeReaders.length > 0 && (
                <div className="rounded-xl border border-blue-500/40 bg-blue-600/10 p-3 space-y-2">
                  {cardPending ? (
                    <div className="flex items-center gap-3">
                      <Loader2 size={22} className="animate-spin text-blue-300 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="font-semibold">{__("Waiting for card on {0}", [cardPending.label])}</p>
                        <p className="text-xs text-muted-foreground tabular-nums">{money(cardPending.amount, currency)}</p>
                      </div>
                      <button onClick={cancelCard} className="px-3 py-2 rounded-lg bg-muted text-sm font-semibold">{__("Cancel")}</button>
                    </div>
                  ) : (
                    <>
                      {activeReaders.length > 1 && (
                        <div className="flex flex-wrap gap-1.5">
                          {activeReaders.map((r) => (
                            <button key={r.reader} onClick={() => setReaderId(r.reader)}
                                    className={`px-2.5 py-1 rounded-lg text-xs border ${r.reader === activeReader?.reader ? "border-blue-500 bg-blue-600/20" : "border-border"}`}>
                              {r.label}
                            </button>
                          ))}
                        </div>
                      )}
                      {splitN <= 1 && (
                        <button
                          onClick={() => startCard(parseFloat(amounts[activeMode]) || remaining)}
                          disabled={paying || tipLoading || remaining <= 0}
                          className="w-full py-3 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold disabled:opacity-40"
                        >
                          {__("Charge {0} on {1}", [money(parseFloat(amounts[activeMode]) || remaining, currency), activeReader?.label])}
                        </button>
                      )}
                    </>
                  )}
                  {cardError && <p className="text-sm text-rose-400">{cardError}</p>}
                  {cardPayments.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {cardPayments.map((c) => (
                        <span key={c.name} className="px-2.5 py-1 rounded-lg text-xs border border-emerald-500/50 bg-emerald-500/10 text-emerald-300 tabular-nums">
                          {c.card || c.mode_of_payment} · {money(c.amount, currency)}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}

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
                    {modeType(activeMode) === "Cash" && cashSuggestions(remaining + (parseFloat(amounts[activeMode]) || 0)).slice(0, 3).map((v) => (
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
                    className="h-11 rounded-xl bg-muted/60 hover:bg-muted active:bg-muted/80 text-2xl font-semibold flex items-center justify-center"
                  >
                    {k === "back" ? <Delete size={20} /> : k}
                  </button>
                ))}
              </div>

              {error && <p className="text-sm text-rose-400">{error}</p>}

              <button
                onClick={charge}
                disabled={!canCharge || paying}
                className={`sticky bottom-5 z-10 mt-auto mb-5 w-full min-h-[72px] flex items-center justify-between gap-3 px-6 rounded-2xl transition-colors shadow-lg
                  ${canCharge && !paying
                    ? "bg-blue-600 hover:bg-blue-500 active:bg-blue-700 text-white shadow-blue-900/40"
                    : "bg-muted text-muted-foreground cursor-not-allowed shadow-none"}`}
              >
                {paying ? (
                  <span className="w-full flex items-center justify-center gap-2 text-xl font-bold">
                    <Loader2 size={22} className="animate-spin" /> {__("Charging…")}
                  </span>
                ) : (
                  <>
                    <span className="flex items-center gap-2 text-xl font-bold">
                      <CreditCard size={22} className="opacity-80" /> {__("Charge")}
                    </span>
                    <span className="text-3xl font-extrabold tabular-nums">{money(due, currency)}</span>
                  </>
                )}
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
      onClose={phase === "done" ? finish : cardPending ? cancelCard : onClose}
      title={header}
      size="lg"
      closeOnEsc={false}
      closeOnOverlay={phase !== "paying"}
      showClose={phase !== "paying"}
    >
      {body}
      {registerOpen && (
        <RegisterPanel
          posProfile={summary?.register?.pos_profile}
          onClose={() => { setRegisterOpen(false); retry(); }}
        />
      )}
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

function TipChip({ children, active, onClick, disabled }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`min-w-[64px] px-3 py-1.5 rounded-lg border text-sm font-semibold text-center transition-colors ${
        active ? "border-blue-500 bg-blue-600/20 text-card-foreground" : "border-border bg-muted/40 hover:bg-muted text-muted-foreground"
      }`}
    >
      {children}
    </button>
  );
}

/**
 * A chip that turns into a numeric field in place ("Custom" tip, "Other"
 * points): digits only (and one decimal point unless `integer`), capped at
 * `max`; Enter or ✓ applies, Esc or leaving it empty cancels.
 */
function NumberChip({ label, active, disabled, initial = "", placeholder, integer = false, max, onApply }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const inputRef = useRef(null);

  const start = () => {
    setText(initial === "" || initial == null ? "" : String(initial));
    setEditing(true);
    setTimeout(() => inputRef.current?.select(), 0);
  };
  const clean = (v) => {
    let out = integer ? v.replace(/\D/g, "") : v.replace(/[^\d.]/g, "").replace(/(\..*)\./g, "$1");
    if (!integer) out = out.replace(/^(\d*\.\d{0,2}).*$/, "$1");
    if (max != null && out !== "" && parseFloat(out) > max) out = String(max);
    return out;
  };
  const apply = () => {
    setEditing(false);
    if (text === "" || text === ".") return;
    onApply(integer ? parseInt(text, 10) : parseFloat(text));
  };

  if (!editing) {
    return <TipChip active={active} disabled={disabled} onClick={start}>{label}</TipChip>;
  }
  return (
    <div className="flex items-stretch rounded-lg border border-blue-500 bg-blue-600/10 overflow-hidden">
      <input
        ref={inputRef}
        autoFocus
        type="text"
        inputMode={integer ? "numeric" : "decimal"}
        pattern={integer ? "[0-9]*" : "[0-9]*[.]?[0-9]*"}
        value={text}
        placeholder={placeholder}
        onChange={(e) => setText(clean(e.target.value))}
        onKeyDown={(e) => {
          if (e.key === "Enter") { e.preventDefault(); apply(); }
          if (e.key === "Escape") { e.stopPropagation(); setEditing(false); }
        }}
        className="w-24 px-2.5 py-1.5 bg-transparent text-sm font-semibold tabular-nums outline-none"
      />
      <button
        onMouseDown={(e) => e.preventDefault()}
        onClick={apply}
        disabled={text === ""}
        aria-label={__("Apply")}
        className="px-2.5 bg-blue-600 text-white disabled:opacity-40"
      >
        <Check size={16} />
      </button>
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
