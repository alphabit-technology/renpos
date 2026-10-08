import { useState } from 'react'
import { ChefHat, Plus, X, ChevronUp } from 'lucide-react'
import { Station } from '../objects/Station.jsx'
import { useRestaurant } from '@/context/RestaurantContext.jsx'
import { useFloors } from '@/context/FloorsContext.jsx'
import { can } from '@/router/permissions'

/**
 * Production centers belong to the floor, not to a room, so they live in a
 * dock beside the plan (tablet / desktop) or in a bottom sheet (phone), the
 * same whichever room is selected. Each row shows what is waiting there by
 * status, with the colors and names configured for the statuses.
 */

function ProductionList({ stations, live, onAdd, compact }) {
  const { editing } = useRestaurant()
  return (
    <div className="flex flex-col gap-2">
      {stations.map((s) => (
        <Station key={s.name} station={s} summary={live.summary[s.name]} offset={live.offset} now={live.now} compact={compact} />
      ))}
      {editing && onAdd && can('station.create') && (
        <button
          onClick={onAdd}
          className="w-full flex items-center justify-center gap-1.5 rounded-lg border border-dashed border-border py-2.5 text-sm text-muted-foreground hover:text-foreground hover:bg-accent/40"
        >
          <Plus size={15} /> {__('Production center')}
        </button>
      )}
    </div>
  )
}

function DockTitle({ floor }) {
  return (
    <div className="flex items-baseline gap-1.5 min-w-0">
      <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">{__('Production')}</span>
      {floor && <span className="text-[11px] text-muted-foreground/70 truncate">· {floor}</span>}
    </div>
  )
}

/** Tablet / desktop: fixed column on the right of the plan. */
export function ProductionDock({ stations, live, onAdd }) {
  const { currentFloor } = useFloors()
  return (
    <aside className="w-60 shrink-0 border-l border-border bg-card/40 flex flex-col min-h-0">
      <div className="px-3 pt-3 pb-2"><DockTitle floor={currentFloor?.description} /></div>
      <div className="flex-1 overflow-y-auto px-2 pb-3">
        <ProductionList stations={stations} live={live} onAdd={onAdd} compact />
      </div>
    </aside>
  )
}

/** Phone: a bar at the bottom with the total waiting; opens a sheet. */
export function ProductionSheet({ stations, live }) {
  const [open, setOpen] = useState(false)
  const { currentFloor } = useFloors()
  const total = stations.reduce((n, s) => n + (live.summary[s.name]?.tickets ?? s.orders_count ?? 0), 0)

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="shrink-0 h-12 flex items-center gap-2 px-4 border-t border-border bg-card text-sm font-medium"
      >
        <ChefHat size={17} className="text-muted-foreground" />
        <span>{__('Production')}</span>
        {total > 0 && (
          <span className="min-w-6 h-6 px-1.5 rounded-full bg-primary text-primary-foreground text-xs font-bold flex items-center justify-center">
            {total}
          </span>
        )}
        <ChevronUp size={16} className="ml-auto text-muted-foreground" />
      </button>

      {/* kept mounted so a station's kitchen screen survives closing the sheet */}
      <div className={`fixed inset-0 z-[300] ${open ? '' : 'pointer-events-none'}`} aria-hidden={!open}>
        <div
          className={`absolute inset-0 bg-black/50 transition-opacity ${open ? 'opacity-100' : 'opacity-0'}`}
          onClick={() => setOpen(false)}
        />
        <div
          className={`absolute left-0 right-0 bottom-0 max-h-[75%] flex flex-col rounded-t-2xl bg-background border-t border-border shadow-2xl
            transition-transform duration-200 ${open ? 'translate-y-0' : 'translate-y-full'}`}
        >
          <div className="flex items-center justify-between px-4 pt-3 pb-2">
            <DockTitle floor={currentFloor?.description} />
            <button onClick={() => setOpen(false)} className="p-1.5 rounded-md hover:bg-accent" aria-label={__('Close')}>
              <X size={18} />
            </button>
          </div>
          <div className="overflow-y-auto px-3 pb-[max(1rem,env(safe-area-inset-bottom))]">
            <ProductionList stations={stations} live={live} />
          </div>
        </div>
      </div>
    </>
  )
}

/** Someone with production centers but no rooms (a cook): the centers are the screen. */
export function ProductionHome({ stations, live }) {
  const { currentFloor } = useFloors()
  return (
    <div className="flex-1 overflow-y-auto p-4">
      <div className="max-w-xl mx-auto flex flex-col gap-3">
        <DockTitle floor={currentFloor?.description} />
        <ProductionList stations={stations} live={live} />
      </div>
    </div>
  )
}
