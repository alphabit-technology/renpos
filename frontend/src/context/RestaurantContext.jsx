import { createContext, useContext, useEffect, useRef, useState } from 'react'
import { usePersistedState } from '@/hooks/usePersistedState'
import {initPermissions, generalCustomAccess} from "@/router/permissions"
import { useFrappeRealtime } from '@/hooks/useFrappeRealtime';


const RestaurantContext = createContext(null)

export function RestaurantProvider({ children }) {

  const [editing, setEditing] = usePersistedState('ren_editing', null)
  const [REN, setREN] = useState({})
  const [ready, setReady] = useState(false)
  const [currentTable, setCurrentTable] = usePersistedState("ren_current_table", null)
  const [settingsUpdate, setSettingsUpdate] = useState(0)
  const [startupError, setStartupError] = useState(null)

  useEffect(() => {
    initPermissions(REN)
    // only once the restaurant data is in: before that REN is {} and the saved
    // edit mode would be wiped on every reload
    if (REN?.permissions && !generalCustomAccess(REN)) setEditing(false)
  }, [REN])


  const callMethod = async (Model, Name, Method, { args = {}, ...options } = {}) => {
    try {
      const response = await frappe.call({
        method: "renpos.api.ren.call",
        args: { model: Model, name: Name, method: Method, args },
        freeze: !!options.freeze
      })
      const data = response.message
      options.callback?.(data)
      options.success?.(data)
      return data
    } catch (error) {
      console.error(`Method Error (${Model}.${Method}):`, error)
      options.error?.(error)
      throw error
    } finally {
      options.always?.()
    }
  }

  const loadSettingData = () => {
    // frappe.call (not xcall): its error callback gets the server message
    new Promise((resolve, reject) => frappe.call({
      method: "renpos.api.restaurant.init_restaurant",
      args: {},
      callback: (res) => resolve(res.message),
      error: reject,
    })).then(r => {
      setREN({ ...r })
      setSettingsUpdate((v) => v + 1)
      setStartupError(null)
      setReady(true)
    }).catch((e) => {
      // e.g. user without POS Profile / restaurant not configured
      setStartupError(_serverMessage(e) || __("The restaurant could not be loaded."))
    })
  }

  useEffect(() => {
    loadSettingData();
  }, [])

  // A print job of this user failed (printer off, paper out, wrong IP…)
  useFrappeRealtime("restaurant_print", (data) => {
    if (!data || data.status !== "Failed" || data.owner !== frappe.session.user) return;
    frappe.confirm(
      __("Printer {0} could not print the {1} ({2}). Try again?", [data.printer, __(data.type), data.error || ""]),
      () => frappe.call({ method: "renpos.api.printing.retry_job", args: { job: data.job } })
    );
  });

  // the setup changed (restaurant, roles, access, floors, stations…; api/sync.py):
  // reload the restaurant data; settingsUpdate tells the rest of the screen
  const configTimer = useRef(0)
  useFrappeRealtime("ren_config", () => {
    clearTimeout(configTimer.current)
    configTimer.current = setTimeout(loadSettingData, 400)
  }, [])

  return (
    <RestaurantContext.Provider value={{
      REN, ready, editing, setEditing, callMethod, currentTable, setCurrentTable,
      restaurant: REN.restaurant,
      settingsUpdate
    }}>
      {ready ? children : startupError ? (
        <div className="flex h-full items-center justify-center p-6">
          <div className="max-w-md rounded-2xl border border-border bg-card p-6 text-center">
            <p className="text-lg font-semibold mb-2">{__("Restaurant setup required")}</p>
            <p className="text-sm text-muted-foreground">{startupError}</p>
          </div>
        </div>
      ) : null}
    </RestaurantContext.Provider>
  )
}

/** First readable message from a failed frappe.call / xcall. */
function _serverMessage(e) {
  try {
    const raw = e?._server_messages || e?.response?._server_messages;
    if (raw) {
      const first = JSON.parse(JSON.parse(raw)[0]);
      return (first.message || "").replace(/<[^>]+>/g, "");
    }
  } catch { /* fall through */ }
  return e?.message && !String(e.message).startsWith("HTTP") ? e.message : null;
}

export const useRestaurant = () => {
  const ctx = useContext(RestaurantContext)
  if (!ctx) throw new Error('useRestaurant debe usarse dentro de RestaurantProvider')
  return ctx
}