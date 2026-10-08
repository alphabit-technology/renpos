/**
 * What the screen shows lives in the URL query string
 * (/app/ren-pos?floor=…&room=…&table=…), so a reload, a bookmark
 * or a fixed kitchen tablet opens the same view.
 *
 * Frappe owns the desk router (/app/<page>); a second router (React Router)
 * would fight it over history. This is one page, so plain query params with
 * history.replaceState are enough: they don't add history entries and
 * Frappe ignores them when matching the page.
 */

export function getUrlParam(key) {
  try {
    return new URLSearchParams(window.location.search).get(key);
  } catch {
    return null;
  }
}

export function setUrlParams(params) {
  try {
    const url = new URL(window.location.href);
    for (const [key, value] of Object.entries(params)) {
      if (value) url.searchParams.set(key, value);
      else url.searchParams.delete(key);
    }
    const next = url.pathname + url.search + url.hash;
    if (next !== window.location.pathname + window.location.search + window.location.hash) {
      window.history.replaceState(window.history.state, "", next);
    }
  } catch {
    /* not in a browser */
  }
}
