// Guest ordering API (renpos/api/online.py). No Frappe desk here: plain fetch.

const BASE = "/api/method/renpos.api.online.";

function messageOf(data, fallback) {
  try {
    if (data?._server_messages) {
      const msgs = JSON.parse(data._server_messages).map((m) => {
        try { return JSON.parse(m).message; } catch { return m; }
      });
      const text = msgs.filter(Boolean).join("\n");
      if (text) return text.replace(/<[^>]+>/g, "");
    }
  } catch { /* fall through */ }
  if (data?.exc_type === "RateLimitExceededError" || data?.exception?.includes?.("RateLimit")) {
    return __("Too many tries. Please wait a few minutes.");
  }
  return fallback;
}

async function call(method, params, post = false) {
  const csrf = window.REN_GUEST?.csrf_token;
  let res;
  try {
    if (post) {
      res = await fetch(BASE + method, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          ...(csrf ? { "X-Frappe-CSRF-Token": csrf } : {}),
        },
        body: JSON.stringify(params),
      });
    } else {
      const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v != null && v !== ""));
      res = await fetch(`${BASE}${method}?${qs}`, { headers: { Accept: "application/json" } });
    }
  } catch {
    throw new Error(__("No connection. Check your internet and try again."));
  }
  let data = null;
  try { data = await res.json(); } catch { /* not json */ }
  if (!res.ok || !data) {
    throw new Error(messageOf(data, res.status === 429
      ? __("Too many tries. Please wait a few minutes.")
      : __("Something went wrong. Please try again.")));
  }
  return data.message;
}

export const GuestAPI = {
  menu: (where) => call("menu", where),
  place: (where, body) => call("place", { ...where, ...body, items: JSON.stringify(body.items) }, true),
  status: (token) => call("status", { token }),
  deliveryCheck: (zipcode) => call("delivery_check", { zipcode }),
};
