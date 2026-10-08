import { useState, useCallback, useTransition } from "react";
import { getUrlParam, setUrlParams } from "@/utils/urlState";
import { useMenuManager } from "./useMenuManager";
import { ItemTree } from "@/components/items";
import Modal from "@c/ui/Modal";
import {
  Plus, ChevronLeft, ChevronRight, Search, Loader2, Pencil,
} from "lucide-react";
import { ItemEditor } from "./src/ItemEditor";

import { MenuList } from "./src/MenuList";
import { TabButton } from "./src/TabButton";

/**
 * Menu — Internal content component.
 *
 * Layout: Left sidebar (menu list) + Right area (single ItemTree).
 *
 * Tab "Items" → ItemTree with no menuName (all items)
 * Tab "Menu"  → ItemTree with menuName (server filters by menu)
 *
 * Both tabs show menuMode=true so ring/check indicates menu membership.
 * Click on item = immediate server toggle (no Save button).
 */
function Menu({ company = frappe.defaults.get_user_default("company"), className = "" }) {
  const mm = useMenuManager(company);
  // tab survives a reload (?menu_tab=menu)
  const [activeTab, setActiveTab] = useState(() => (getUrlParam("menu_tab") === "menu" ? "menu" : "items"));
  const [isPending, startTransition] = useTransition();
  const [showNewMenu, setShowNewMenu] = useState(false);
  const [newMenuName, setNewMenuName] = useState("");
  const [sidebarSearch, setSidebarSearch] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(null);
  // item editor: { code } to edit, { code: null } for a new item
  const [editing, setEditing] = useState(null);

  // the pencil on every card opens the item editor (a tap on the card still adds / removes it)
  const renderEdit = useCallback((item) => (
    <span
      role="button" tabIndex={0} title={__("Edit item")}
      onClick={(e) => { e.stopPropagation(); setEditing({ code: item.item_code }); }}
      onKeyDown={(e) => { if (e.key === "Enter") { e.stopPropagation(); setEditing({ code: item.item_code }); } }}
      className="w-7 h-7 rounded-lg bg-black/40 hover:bg-black/60 text-white/90 flex items-center justify-center backdrop-blur-sm"
    >
      <Pencil size={13} />
    </span>
  ), []);

  // The only difference between tabs: menuName or null
  const currentMenuName = activeTab === "menu" ? mm.activeMenuName : null;

  const switchTab = useCallback((tab) => {
    setUrlParams({ menu_tab: tab === "menu" ? "menu" : null });
    startTransition(() => {
      setActiveTab(tab);
    });
  }, [startTransition]);

  const handleCreateMenu = useCallback(() => {
    const name = newMenuName.trim();
    if (!name) return;
    mm.addMenu(name).then(() => {
      setNewMenuName("");
      setShowNewMenu(false);
    });
  }, [newMenuName, mm]);

  const handleDeleteConfirm = useCallback((menuName) => {
    mm.removeMenu(menuName);
    setConfirmDelete(null);
  }, [mm]);

  const handleSidebarSearch = useCallback((e) => {
    const val = e.target.value;
    setSidebarSearch(val);
    mm.searchMenus(val);
  }, [mm]);

  return (
    <div className={`flex h-full bg-background ${className}`}>
      {/* ── LEFT SIDEBAR ── */}
      <aside className="w-64 shrink-0 flex flex-col border-r border-border bg-card">
        {/* Header */}
        <div className="px-3 py-3 border-b border-border">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-card-foreground">{__("Menus")}</h3>
            <button
              onClick={() => setShowNewMenu(true)}
              className="flex items-center gap-1 text-[11px] font-medium px-2 py-1 rounded-md
                         bg-accent text-accent-foreground hover:bg-accent/80 transition-colors"
            >
              <Plus size={12} />
              {__("New")}
            </button>
          </div>
          <div className="relative">
            <Search size={13} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              value={sidebarSearch}
              onChange={handleSidebarSearch}
              placeholder={__("Search menus...")}
              className="w-full pl-7 pr-2 py-1.5 text-xs rounded-md bg-muted/50 border border-border
                         text-card-foreground placeholder:text-muted-foreground
                         focus:outline-none focus:ring-1 focus:ring-ring/40"
            />
          </div>
        </div>

        {showNewMenu && (
          <div className="px-3 py-2 border-b border-border bg-muted/30">
            <input
              type="text"
              value={newMenuName}
              onChange={(e) => setNewMenuName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreateMenu()}
              placeholder={__("Menu name...")}
              autoFocus
              className="w-full px-2 py-1.5 text-xs rounded-md bg-background border border-border
                         text-card-foreground placeholder:text-muted-foreground
                         focus:outline-none focus:ring-1 focus:ring-ring/40 mb-2"
            />
            <div className="flex gap-1.5">
              <button
                onClick={handleCreateMenu}
                disabled={!newMenuName.trim()}
                className="flex-1 text-[11px] font-medium py-1 rounded-md bg-emerald-600 text-white
                           hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {__("Create")}
              </button>
              <button
                onClick={() => { setShowNewMenu(false); setNewMenuName(""); }}
                className="px-2 py-1 text-[11px] rounded-md text-muted-foreground hover:bg-muted transition-colors"
              >
                {__("Cancel")}
              </button>
            </div>
          </div>
        )}

        <div className="flex-1 overflow-y-auto">
          {mm.listLoading && mm.menus.length === 0 ? (
            <div className="flex items-center justify-center h-20">
              <Loader2 size={16} className="animate-spin text-muted-foreground" />
            </div>
          ) : mm.menus.length === 0 ? (
            <div className="px-3 py-6 text-center">
              <p className="text-xs text-muted-foreground mb-2">{__("No menus yet")}</p>
              <button onClick={() => setShowNewMenu(true)} className="text-xs text-accent-foreground hover:underline">
                {__("Create your first menu")}
              </button>
            </div>
          ) : (
            <div className="py-1">
              {mm.menus.map((menu) => (
                <MenuList
                  key={menu.name}
                  menu={menu}
                  isActive={mm.activeMenuName === menu.name}
                  onSelect={() => mm.selectMenu(menu.name)}
                  onSetDefault={() => mm.setAsDefault(menu.name)}
                  onToggleEnabled={() => mm.toggleMenuEnabled(menu.name)}
                  onDelete={() => setConfirmDelete(menu.name)}
                />
              ))}
            </div>
          )}
        </div>

        {mm.totalPages > 1 && (
          <div className="px-3 py-2 border-t border-border flex items-center justify-between">
            <button onClick={mm.prevPage} disabled={!mm.hasPrevPage}
              className="p-1 rounded hover:bg-muted disabled:opacity-30 transition-colors">
              <ChevronLeft size={14} />
            </button>
            <span className="text-[10px] text-muted-foreground tabular-nums">
              {mm.listPage + 1} / {mm.totalPages}
            </span>
            <button onClick={mm.nextPage} disabled={!mm.hasNextPage}
              className="p-1 rounded hover:bg-muted disabled:opacity-30 transition-colors">
              <ChevronRight size={14} />
            </button>
          </div>
        )}
      </aside>

      <main className="flex-1 flex flex-col min-w-0">
        {mm.activeMenuName ? (
          <>
            <div className="shrink-0 flex items-center px-4 py-2 border-b border-border">
              <TabButton
                active={activeTab === "items"}
                onClick={() => switchTab("items")}
                label={__("Items")}
                subtitle={__("All")}
              />
              <TabButton
                active={activeTab === "menu"}
                onClick={() => switchTab("menu")}
                label={__("Menu")}
                subtitle={`${mm.menuItems.size}`}
              />
              {isPending && (
                <Loader2 size={12} className="animate-spin text-muted-foreground ml-2" />
              )}
              <button
                onClick={() => setEditing({ code: null })}
                className="ml-auto flex items-center gap-1.5 h-9 px-3 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold"
              >
                <Plus size={15} /> {__("New item")}
              </button>
            </div>

            <ItemTree
              enabled={true}
              className="flex-1"
              onItemClick={mm.toggleItem}
              menuName={currentMenuName}
              menuItems={mm.menuItems}
              menuMode={true}
              showOrderQty={false}
              renderAction={renderEdit}
            />
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center">
            <p className="text-sm text-muted-foreground">
              {mm.menus.length === 0
                ? __("Create a menu to get started")
                : __("Select a menu")}
            </p>
          </div>
        )}
      </main>

      {editing && (
        <ItemEditor
          itemCode={editing.code}
          menu={mm.activeMenuName}
          onClose={() => setEditing(null)}
          onSaved={() => { mm.selectMenu(mm.activeMenuName); mm.refreshList(); }}
        />
      )}

      {confirmDelete && (
        <ConfirmDialog
          message={__("Delete menu '{0}'?", [confirmDelete])}
          onConfirm={() => handleDeleteConfirm(confirmDelete)}
          onCancel={() => setConfirmDelete(null)}
        />
      )}
    </div>
  );
}

function ConfirmDialog({ message, onConfirm, onCancel }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-card rounded-xl p-5 shadow-xl max-w-sm w-full mx-4 border border-border">
        <p className="text-sm text-card-foreground mb-4">{message}</p>
        <div className="flex gap-2 justify-end">
          <button onClick={onCancel}
            className="px-3 py-1.5 text-xs rounded-lg text-muted-foreground hover:bg-muted transition-colors">
            {__("Cancel")}
          </button>
          <button onClick={onConfirm}
            className="px-3 py-1.5 text-xs font-medium rounded-lg bg-destructive text-destructive-foreground
                       hover:bg-destructive/90 transition-colors">
            {__("Delete")}
          </button>
        </div>
      </div>
    </div>
  );
}

export function MenuManager({ open, onClose, ...props }) {
  if (!open) return null;
  return (
    <Modal size="full" title="Menu Manager" onClose={onClose} open={open}>
      <Menu {...props} />
    </Modal>
  );
}

export default MenuManager;