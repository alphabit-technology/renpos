import { Plus } from 'lucide-react'
import Modal from "@c/ui/Modal"
import { ItemTree } from '@/components/items'

export function OrderManage() {
  return (
      <div className="flex h-screen overflow-hidden bg-[var(--card-bg,#1a1a2e)] text-[var(--text-color,#e0e0e0)]">

        {/* ── Left Sidebar: Order Tabs ── */}
        <aside className="w-16 shrink-0 flex flex-col items-center gap-2 py-3 border-r border-white/10">
          <button className="w-10 h-10 rounded-lg border border-white/15 flex items-center justify-center text-[var(--text-muted,#888)] hover:bg-white/10 transition-all">
            <Plus size={18} />
          </button>

          {/* Order tabs go here */}
          <div className="flex-1 overflow-y-auto w-full flex flex-col items-center gap-1.5 py-1" />
        </aside>

        {/* ── Center: Items Panel ── */}
        <main className="flex-1 flex flex-col min-w-0 border-r border-white/10">
          <ItemTree/>
        </main>

        {/* ── Right: Order Detail Panel ── */}
        <aside className="w-[380px] shrink-0 flex flex-col">

          {/* Order items list */}
          <div className="flex-1 overflow-y-auto border-b border-white/10">
            {/* Selected items */}
          </div>

          {/* Numpad + Actions */}
          <div className="shrink-0 flex">

            {/* Numpad */}
            <div className="flex-1 p-2">
              {/* Qty / Discount / Rate row */}
              {/* Number grid */}
              {/* Total */}
            </div>

            {/* Action buttons */}
            <div className="w-28 shrink-0 flex flex-col border-l border-white/10">
              {/* Order, Account, Divide, Transfer, Complete */}
            </div>
          </div>
        </aside>
      </div>
  )
}

export function OrderManager({open, onClose, ...props}){
  if(!open) return null;

  return (
    <Modal size="full" title={__("Order Manage")} onClose={onClose} open={open}>
      <Order {...props}/>
    </Modal>
  )
}