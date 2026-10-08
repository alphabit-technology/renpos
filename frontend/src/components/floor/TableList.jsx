import { useMemo, useState } from 'react'
import { Search, X, UtensilsCrossed } from 'lucide-react'
import { Table, tableState } from '../objects/Table.jsx'
import { usePersistedState } from '@/hooks/usePersistedState'

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'free', label: 'Free' },
  { key: 'mine', label: 'Yours' },
  { key: 'occupied', label: 'Occupied' },
  { key: 'reserved', label: 'Reserved' },
]

const byName = (a, b) => String(a.description || a.name).localeCompare(String(b.description || b.name), undefined, { numeric: true })

/**
 * The room's tables as a list of cards, like a delivery app: search,
 * quick filters by state and big touch targets. Same tables, same live
 * updates and the same order screen as the plan.
 */
export function TableList({ tables, room, tools }) {
  const [query, setQuery] = useState('')
  const [filter, setFilter] = usePersistedState('ren_table_filter', 'all')

  const counts = useMemo(() => {
    const c = { all: tables.length, free: 0, mine: 0, occupied: 0, reserved: 0 }
    tables.forEach((t) => { c[tableState(t)] += 1 })
    // "occupied" includes yours: it's every table with an open order
    c.occupied += c.mine
    return c
  }, [tables])

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    return tables
      .filter((t) => {
        const s = tableState(t)
        if (filter === 'occupied' ? !(s === 'occupied' || s === 'mine') : filter !== 'all' && s !== filter) return false
        if (!q) return true
        return [t.description, t.name, t.customer, t.reservation?.guest].some((v) => String(v || '').toLowerCase().includes(q))
      })
      .sort(byName)
  }, [tables, query, filter])

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="shrink-0 flex flex-col gap-2 px-3 pt-3 pb-2">
        <div className="flex items-center gap-2">
          <label className="flex-1 flex items-center gap-2 h-10 px-3 rounded-lg border border-border bg-card">
            <Search size={16} className="text-muted-foreground shrink-0" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={__('Table, guest…')}
              className="flex-1 min-w-0 bg-transparent outline-none text-sm"
            />
            {query && <button onClick={() => setQuery('')} aria-label={__('Clear')}><X size={15} className="text-muted-foreground" /></button>}
          </label>
          {tools}
        </div>
        <div className="flex gap-1.5 overflow-x-auto -mx-3 px-3" style={{ scrollbarWidth: 'none' }}>
          {FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`shrink-0 h-8 px-3 rounded-full text-xs font-semibold border transition-colors ${
                filter === f.key ? 'bg-foreground text-background border-foreground' : 'border-border text-muted-foreground hover:text-foreground'
              }`}
            >
              {__(f.label)} <span className="opacity-60 ml-0.5">{counts[f.key]}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-3 pb-4">
        {shown.length ? (
          <div className="grid gap-2.5 grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
            {shown.map((t) => (
              <Table key={t.name} variant="card" table={{ ...t, room }} />
            ))}
          </div>
        ) : (
          <div className="h-full min-h-40 flex flex-col items-center justify-center gap-2 text-muted-foreground">
            <UtensilsCrossed size={36} className="opacity-50" />
            <span className="text-sm">{tables.length ? __('No tables match') : __('No tables in this room')}</span>
          </div>
        )}
      </div>
    </div>
  )
}
