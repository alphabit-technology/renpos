/**
 * Manager approval with a PIN.
 *
 * When the person's Ren Role doesn't allow an action, the server
 * answers ApprovalRequired with the action (approval_action). We ask for the
 * PIN of someone whose role allows it, get a one-time token
 * (renpos.api.access.approve) and repeat the call with it.
 */

const APPROVE = "renpos.api.access.approve";

let open = null; // one PIN dialog at a time

// what the manager is approving, shown before they type their PIN
function describe({ label, action, amount, detail, reference }) {
  const esc = frappe.utils.escape_html;
  const lines = [`<b>${esc(__("Approve: {0}", [label || action]))}</b>`];
  if (detail) lines.push(esc(detail));
  if (amount !== undefined && amount !== null) {
    lines.push(action === "discount" ? esc(__("Discount: {0}%", [amount]))
      : action === "change_price" ? esc(__("New price: {0}", [window.format_currency(amount)]))
        : esc(__("Amount: {0}", [window.format_currency(amount)])));
  }
  if (reference) lines.push(`<span class="text-muted">${esc(__("Order {0}", [String(reference).slice(-5)]))}</span>`);
  return `<div style="line-height:1.6">${lines.join("<br>")}</div>`;
}

export function requestApproval(action, label, amount, extra = {}) {
  if (open) return open;
  open = new Promise((resolve) => {
    const d = new frappe.ui.Dialog({
      title: __("Manager approval"),
      fields: [
        { fieldtype: "HTML", fieldname: "info",
          options: describe({ action, label, amount, detail: extra.detail, reference: extra.reference }) },
        { fieldtype: "Password", fieldname: "pin", label: __("Manager PIN"), reqd: 1 },
      ],
      primary_action_label: __("Approve"),
      primary_action: async ({ pin }) => {
        try {
          const r = await frappe.call({ method: APPROVE, args: { action, pin, amount, reference: extra.reference } });
          const token = r.message?.approval;
          if (token) {
            frappe.show_alert({ message: __("Approved by {0}", [r.message.approver]), indicator: "green" });
            done(token);
          }
        } catch {
          d.set_value("pin", "");
        }
      },
      secondary_action_label: __("Cancel"),
      secondary_action: () => done(null),
    });
    let settled = false;
    const done = (token) => {
      if (settled) return;
      settled = true;
      d.hide();
      open = null;
      resolve(token);
    };
    d.onhide = () => done(null);
    d.show();
    setTimeout(() => d.$wrapper.find("input[data-fieldname=pin]").attr("inputmode", "numeric").focus(), 200);
  });
  return open;
}

/** frappe.call that asks for a manager PIN when the server needs an approval, then retries once. */
export function callWithApproval(method, args = {}) {
  const run = (extra) => new Promise((resolve, reject) => {
    frappe.call({
      method,
      args: { ...args, ...extra },
      callback: (r) => resolve(r.message),
      error: (r) => reject(r),
    });
  });
  // a call may need more than one approval (e.g. someone else's order, then a discount): up to 3
  const attempt = async (extra, left) => {
    try {
      return await run(extra);
    } catch (r) {
      if (r?.exc_type !== "ApprovalRequired" || !r.approval_action || left <= 0) throw r;
      const token = await requestApproval(r.approval_action, r.approval_label, r.approval_amount,
        { reference: r.approval_reference, detail: r.approval_detail });
      if (!token) throw r;
      return attempt({ approval: token }, left - 1);
    }
  };
  return attempt({}, 3);
}
