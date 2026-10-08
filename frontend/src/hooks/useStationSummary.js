import { useCallback, useEffect, useRef, useState } from 'react'

const EVENTS = ['kitchen_order', 'kitchen_update', 'order_update', 'ren_config']

/**
 * Live summary of a floor's production centers for the floor plan:
 * {station: {tickets, oldest, statuses: [{status, label, color, count}]}}.
 * Refreshed when an order is sent or a line changes status (debounced), and
 * every 30 s as a safety net. `now` ticks every 30 s for the waiting times. `offset` = server clock − device clock (ms),
 * to show how long the oldest ticket has been waiting.
 */
export function useStationSummary(floor, enabled = true) {
  const [summary, setSummary] = useState({})
  const [offset, setOffset] = useState(0)
  const [now, setNow] = useState(() => Date.now())
  const timer = useRef(0)

  const load = useCallback(() => {
    if (!floor || !enabled) return
    frappe.call({
      method: 'renpos.api.kitchen.get_floor_summary',
      args: { floor },
    }).then((r) => {
      const m = r.message || {}
      setSummary(m.stations || {})
      setNow(Date.now())
      if (m.server_time) {
        const server = new Date(String(m.server_time).replace(' ', 'T')).getTime()
        if (!Number.isNaN(server)) setOffset(server - Date.now())
      }
    }, () => {})
  }, [floor, enabled])

  useEffect(() => {
    load()
    if (!floor || !enabled) return undefined
    const schedule = () => {
      clearTimeout(timer.current)
      timer.current = setTimeout(load, 600)
    }
    frappe.realtime.doctype_subscribe?.('Ren Order')
    EVENTS.forEach((e) => frappe.realtime.on(e, schedule))
    const poll = setInterval(load, 30000)
    const tick = setInterval(() => setNow(Date.now()), 30000)
    return () => {
      clearTimeout(timer.current)
      clearInterval(poll)
      clearInterval(tick)
      EVENTS.forEach((e) => frappe.realtime.off(e, schedule))
    }
  }, [floor, enabled, load])

  return { summary, offset, now, reload: load }
}

/** Minutes since a server datetime, given the clock offset and the current device time. */
export function minutesSince(datetime, offset, now) {
  if (!datetime) return null
  const t = new Date(String(datetime).replace(' ', 'T')).getTime()
  if (Number.isNaN(t)) return null
  return Math.max(0, Math.floor((now + offset - t) / 60000))
}
