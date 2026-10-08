import { Settings, Trash2, ChefHat, Clock } from 'lucide-react'

import { ActionButton } from '@c/ui/ActionButton.jsx'
import { useRestaurant } from '@/context/RestaurantContext.jsx'
import { useState } from 'react'
import { getUrlParam, setUrlParams } from '@/utils/urlState'
import { KitchenView } from '@c/kitchen/KitchenView.jsx'
import { can } from '@/router/permissions'
import { minutesSince } from '@/hooks/useStationSummary'

/** 7′ · 1h 20′ · 2d */
function formatWait(m) {
  if (m == null) return ''
  if (m < 60) return `${m}′`
  if (m < 24 * 60) return `${Math.floor(m / 60)}h${m % 60 ? ` ${m % 60}′` : ''}`
  return `${Math.floor(m / 1440)}d`
}

function Waited({ minutes }) {
  if (minutes == null) return null
  const tone = minutes >= 20 ? 'text-red-400' : minutes >= 10 ? 'text-amber-400' : 'text-muted-foreground'
  return (
    <span title={__('Oldest ticket')} className={`flex items-center gap-0.5 text-[11px] tabular-nums ${tone}`}>
      <Clock size={11} />{formatWait(minutes)}
    </span>
  )
}

const tint = (color, pct) => `color-mix(in srgb, ${color || '#64748b'} ${pct}%, transparent)`

/**
 * A production center as a row of the production dock (it isn't drawn on
 * the floor plan: it belongs to the floor, not to a room). Tapping it opens
 * its kitchen screen; while editing the floor, its settings.
 *
 * summary: {tickets, oldest, statuses: [{status, label, color, count}]}
 */
export function Station({ station, summary, offset = 0, now = 0, compact = false }) {
  const { callMethod, editing } = useRestaurant()
  // reopened after a reload when the URL says this station was open (?station=…)
  const [kitchenOpen, setKitchenOpenState] = useState(() => getUrlParam('station') === station.name)
  const setKitchenOpen = (open) => {
    setKitchenOpenState(open)
    setUrlParams({ station: open ? station.name : null, table: null })
  }

  const handleStationEdit = () => {
    MetaForm.open('Ren Station', station.name, {
      fieldProperties: {
        floor: { read_only: 1, hidden: 1 }
      },
    })
  }

  const handleStationDelete = () => {
    callMethod("Ren Station", station.name, "delete")
  }

  const activate = () => (editing ? handleStationEdit() : setKitchenOpen(true))
  const tickets = summary?.tickets ?? station.orders_count ?? 0
  const waited = tickets ? minutesSince(summary?.oldest, offset, now) : null
  const color = station.color || '#9f4c5c'

  return (
    <>
      {kitchenOpen && <KitchenView open station={station} onClose={() => setKitchenOpen(false)} />}
      <div
        role="button"
        tabIndex={0}
        onClick={activate}
        onKeyDown={(e) => { if (e.key === 'Enter') activate() }}
        className={`group relative w-full flex items-stretch gap-3 rounded-lg border border-border bg-card
          hover:bg-accent/60 active:scale-[0.99] transition cursor-pointer select-none text-left
          ${compact ? 'p-2.5' : 'p-3'}`}
      >
        <span className="w-1 rounded-full shrink-0" style={{ backgroundColor: color }} />
        <div className="flex-1 min-w-0 flex flex-col gap-1.5">
          <div className="flex items-center gap-2 min-w-0">
            <ChefHat size={15} className="shrink-0 text-muted-foreground" />
            <span className="font-semibold truncate">{station.description}</span>
          </div>
          {editing ? (
            <span className="text-xs text-muted-foreground">{__('Tap to configure')}</span>
          ) : summary?.statuses?.length ? (
            <div className="flex flex-wrap items-center gap-1">
              {summary.statuses.map((s) => (
                <span
                  key={s.status}
                  className="text-[11px] font-semibold rounded px-1.5 py-0.5 leading-tight"
                  style={{ backgroundColor: tint(s.color, 22), boxShadow: `inset 2px 0 0 ${s.color || '#64748b'}` }}
                >
                  {s.count} {__(s.label)}
                </span>
              ))}
              <Waited minutes={waited} />
            </div>
          ) : (
            <span className="text-xs text-muted-foreground">{tickets ? __('{0} waiting', [tickets]) : __('Nothing waiting')}</span>
          )}
        </div>
        {!editing && tickets > 0 && (
          <span className="self-center min-w-7 h-7 px-1.5 rounded-full flex items-center justify-center text-sm font-bold text-white"
            style={{ backgroundColor: color }}>
            {tickets}
          </span>
        )}
        {editing && (
          <div className="self-center flex items-center" onClick={(e) => e.stopPropagation()}>
            {can('station.write') && (
              <ActionButton variant="primary" icon={Settings} onClick={handleStationEdit} className="rounded-none" />
            )}
            {can('station.delete') && (
              <ActionButton variant="primary" icon={Trash2} confirm onClick={handleStationDelete} className="rounded-none" />
            )}
          </div>
        )}
      </div>
    </>
  )
}
