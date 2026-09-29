/**
 * Item catalog constants — shared across ItemCard, ItemGrid, ItemTree.
 *
 * Category colors follow the Square/Toast pattern:
 * each item group gets a distinct color for instant visual recognition.
 *
 * Colors are defined as Tailwind classes for zero-runtime cost.
 * The `stripe` field is the left-edge color used in tile view.
 * The `accent` field is a raw hex value for SVG/canvas use.
 *
 * AUTO-COLOR: Groups not in the manual palette get a color automatically
 * assigned via a deterministic hash — so "Drink" always gets the same
 * color across sessions without manual mapping.
 */

// ─── View modes ──────────────────────────────────
export const VIEW_MODES = {
  tile: { key: "tile", label: __("Tile"), icon: "fa-th-large", minColWidth: 130 },
  image: { key: "image", label: __("Image"), icon: "fa-image", minColWidth: 120 },
  compact: { key: "compact", label: __("Compact"), icon: "fa-list", minColWidth: 180 },
};

export const DEFAULT_VIEW_MODE = "tile";

// ─── Color palette (ordered for maximum contrast between neighbors) ──
const COLOR_PALETTE = [
  { bg: "bg-amber-500/15",   ring: "ring-amber-500/60",   text: "text-amber-400",   dot: "bg-amber-500",   stripe: "bg-amber-500",   accent: "#f59e0b" },
  { bg: "bg-sky-500/15",     ring: "ring-sky-500/60",     text: "text-sky-400",     dot: "bg-sky-500",     stripe: "bg-sky-500",     accent: "#0ea5e9" },
  { bg: "bg-rose-500/15",    ring: "ring-rose-500/60",    text: "text-rose-400",    dot: "bg-rose-500",    stripe: "bg-rose-500",    accent: "#f43f5e" },
  { bg: "bg-emerald-500/15", ring: "ring-emerald-500/60", text: "text-emerald-400", dot: "bg-emerald-500", stripe: "bg-emerald-500", accent: "#10b981" },
  { bg: "bg-violet-500/15",  ring: "ring-violet-500/60",  text: "text-violet-400",  dot: "bg-violet-500",  stripe: "bg-violet-500",  accent: "#8b5cf6" },
  { bg: "bg-orange-500/15",  ring: "ring-orange-500/60",  text: "text-orange-400",  dot: "bg-orange-500",  stripe: "bg-orange-500",  accent: "#f97316" },
  { bg: "bg-teal-500/15",    ring: "ring-teal-500/60",    text: "text-teal-400",    dot: "bg-teal-500",    stripe: "bg-teal-500",    accent: "#14b8a6" },
  { bg: "bg-pink-500/15",    ring: "ring-pink-500/60",    text: "text-pink-400",    dot: "bg-pink-500",    stripe: "bg-pink-500",    accent: "#ec4899" },
  { bg: "bg-cyan-500/15",    ring: "ring-cyan-500/60",    text: "text-cyan-400",    dot: "bg-cyan-500",    stripe: "bg-cyan-500",    accent: "#06b6d4" },
  { bg: "bg-yellow-500/15",  ring: "ring-yellow-500/60",  text: "text-yellow-400",  dot: "bg-yellow-500",  stripe: "bg-yellow-500",  accent: "#eab308" },
  { bg: "bg-indigo-500/15",  ring: "ring-indigo-500/60",  text: "text-indigo-400",  dot: "bg-indigo-500",  stripe: "bg-indigo-500",  accent: "#6366f1" },
  { bg: "bg-lime-500/15",    ring: "ring-lime-500/60",    text: "text-lime-400",    dot: "bg-lime-500",    stripe: "bg-lime-500",    accent: "#84cc16" },
  { bg: "bg-fuchsia-500/15", ring: "ring-fuchsia-500/60", text: "text-fuchsia-400", dot: "bg-fuchsia-500", stripe: "bg-fuchsia-500", accent: "#d946ef" },
  { bg: "bg-red-500/15",     ring: "ring-red-500/60",     text: "text-red-400",     dot: "bg-red-500",     stripe: "bg-red-500",     accent: "#ef4444" },
];

// ─── Manual overrides (optional — takes priority over auto-color) ────
// Keys should match `item_group` values from your Item Group doctype.
const CATEGORY_OVERRIDES = {
  // Uncomment and customize for your restaurant:
  // "Platos Fuertes": COLOR_PALETTE[0],  // amber
  // "Bebidas":        COLOR_PALETTE[1],  // sky
  // "Entradas":       COLOR_PALETTE[3],  // emerald
  // "Postres":        COLOR_PALETTE[4],  // violet
};

const DEFAULT_CATEGORY_COLOR = {
  bg: "bg-zinc-500/15",
  ring: "ring-zinc-500/60",
  text: "text-zinc-400",
  dot: "bg-zinc-500",
  stripe: "bg-zinc-500",
  accent: "#71717a",
};

// ─── Deterministic hash for auto-color assignment ────────────────────
// Same string always produces the same index → consistent colors.
function hashString(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) - hash + str.charCodeAt(i)) | 0;
  }
  return Math.abs(hash);
}

// Cache auto-assigned colors so we don't rehash every render
const _autoColorCache = new Map();

/**
 * Get color scheme for an item group.
 *
 * Priority:
 * 1. Manual override (CATEGORY_OVERRIDES)
 * 2. Auto-assigned from palette via hash
 * 3. Default zinc for null/undefined groups
 */
export function getCategoryColor(itemGroup) {
  if (!itemGroup) return DEFAULT_CATEGORY_COLOR;

  // 1. Check manual overrides
  if (CATEGORY_OVERRIDES[itemGroup]) {
    return CATEGORY_OVERRIDES[itemGroup];
  }

  // 2. Check cache
  if (_autoColorCache.has(itemGroup)) {
    return _autoColorCache.get(itemGroup);
  }

  // 3. Auto-assign via hash
  const index = hashString(itemGroup) % COLOR_PALETTE.length;
  const color = COLOR_PALETTE[index];
  _autoColorCache.set(itemGroup, color);
  return color;
}

/**
 * Register a custom category color at runtime.
 * Useful if item groups are loaded dynamically from the server.
 *
 * Usage:
 *   registerCategoryColor("Sushi", {
 *     bg: "bg-pink-500/15", ring: "ring-pink-500/25",
 *     text: "text-pink-400", dot: "bg-pink-500",
 *     stripe: "bg-pink-500", accent: "#ec4899"
 *   });
 */
export function registerCategoryColor(groupName, colorDef) {
  CATEGORY_OVERRIDES[groupName] = { ...DEFAULT_CATEGORY_COLOR, ...colorDef };
  _autoColorCache.delete(groupName); // clear cache so override takes effect
}

/**
 * Get the full palette for UI (e.g. color picker in settings).
 */
export function getColorPalette() {
  return COLOR_PALETTE;
}