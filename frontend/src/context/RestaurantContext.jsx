import { createContext, useContext, useEffect, useState } from 'react'
import { usePersistedState } from '@/hooks/usePersistedState'
import {initPermissions, generalCustomAccess} from "@/router/permissions"
import {createOpeningVoucher} from "./voucher.js"
import { useFrappeRealtime } from '@/hooks/useFrappeRealtime';


const RestaurantContext = createContext(null)
const API_BASE = "restaurant_management.restaurant_management.page.restaurant_manage.restaurant_manage."

export function RestaurantProvider({ children, posWrapper }) {

  const [editing, setEditing] = usePersistedState('ren_editing', null)
  const [RM, setRM] = useState({})
  const [ready, setReady] = useState(false)
  const [currentTable, setCurrentTable] = usePersistedState("ren_current_table", null)
  const [POS, setPOS] = useState(null);
  const [settingsUpdate, setSettingsUpdate] = useState(0)
  const [startupError, setStartupError] = useState(null)

  useEffect(() => {
    initPermissions(RM)
    if(!generalCustomAccess(RM)) setEditing(false)
  }, [RM])


  const callMethod = async (Model, Name, Method, { args = {}, ...options } = {}) => {
    try {
      const response = await frappe.call({
        method: "restaurant_management.api.ren.call",
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

  useFrappeRealtime("check_floors", () => {
    callMethod("Ren Restaurant", RM?.restaurant.name, "load_floors").then(r => {
      setRM(prev => {
        return { ...prev, floors: r };
      });
    })
  }, [RM?.restaurant?.name]);

  const callApi = async (method, args = {}) => {
    try {
      const response = await frappe.call({
        method: `${API_BASE}${method}`,
        args
      })
      return response.message
    } catch (error) {
      console.error(`API Error (${method}):`, error)
      throw error
    }
  }

  const handleSetPOS = () => {

  }

  const checkOpeningEntry = async () => {
    return new Promise((resolve) => {
      frappe.call("erpnext.selling.page.point_of_sale.point_of_sale.check_opening_entry", {
        user: frappe.session.user,
      }).then(async r => {
        if(r.message.length){
          resolve(true);
        }else{
          resolve(await createOpeningVoucher());
        }
      })
    })
	}

  const loadSettingData = () => {
    // frappe.call (not xcall): its error callback gets the server message
    new Promise((resolve, reject) => frappe.call({
      method: "restaurant_management.api.restaurant.init_restaurant",
      args: {},
      callback: (res) => resolve(res.message),
      error: reject,
    })).then(r => {
      // Startup check: which frontend build and backend version are running
      console.info(
        "%c[Restaurant]%c started",
        "background:#2563eb;color:#fff;padding:2px 6px;border-radius:3px", "",
        {
          frontend_build: __RM_BUILD__,
          backend: r?._server || "OLD backend (no _server marker)",
          realtime_connected: !!frappe.realtime?.socket?.connected,
        }
      )
      const rm = { ...r }
      window.cur_pos = rm.pos;
      rm.crm_settings = {}
      setRM(rm)
      setSettingsUpdate(settingsUpdate+1)
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

  useFrappeRealtime("on_pos_profile_change", () => {
    loadSettingData();
  }, [RM])

  return (
    <RestaurantContext.Provider value={{
      RM, ready, editing, setEditing, callMethod, callApi, API_BASE, currentTable, setCurrentTable,
      POS, handleSetPOS, checkOpeningEntry,
      restaurant: RM.restaurant,
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