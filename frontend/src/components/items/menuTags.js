import { useEffect, useState } from "react";

// Menu Tags (dietary & allergens), loaded once per page
let cache = null;

export function loadMenuTags() {
  if (!cache) {
    cache = frappe.call({ method: "renpos.api.menus.get_menu_tags" })
      .then((r) => r.message || [], () => { cache = null; return []; });
  }
  return cache;
}

export function useMenuTags() {
  const [tags, setTags] = useState([]);
  useEffect(() => {
    let alive = true;
    loadMenuTags().then((t) => { if (alive) setTags(t); });
    return () => { alive = false; };
  }, []);
  return tags;
}
