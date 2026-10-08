import { useRestaurant } from '../../context/RestaurantContext.jsx'
import { Table } from '../objects/Table.jsx'
import { TableList } from './TableList.jsx'
import { ProductionDock, ProductionSheet, ProductionHome } from './ProductionDock.jsx'
import { useStationSummary } from '@/hooks/useStationSummary'
import { useIsMobile } from '@c/order/hooks/useIsMobile'
import { usePersistedState } from '@/hooks/usePersistedState'
import { can } from '@/router/permissions'
import {useRooms} from "@/context/RoomsContext.jsx"
import {useFloors} from "@/context/FloorsContext.jsx"
import { ReservationsBoard } from "@c/booking/ReservationsBoard"

import {
  AddTableButton,
  EditRoomButton,
  DeleteRoomButton,
  MenuButton,
  BookingButton
} from './FloorActions.jsx'

import { UtensilsCrossed, LayoutGrid, Map as MapIcon } from 'lucide-react'
import { useState } from 'react'
import { getUrlParam, setUrlParams } from '@/utils/urlState'
import {MenuManager} from "../menu/MenuManager.jsx"

export function FloorMap() {
  const { setCurrentTable, editing, callMethod, REN } = useRestaurant()
  const { currentFloor, tables, stations, rooms, loadObjects } = useFloors()
  const { currentRoom } = useRooms()
  const isMobile = useIsMobile()
  // plan (the floor drawn to scale) or list (cards, like a delivery app):
  // remembered per device; phones start with the list. Editing is on the plan.
  const [storedView, setView] = usePersistedState('ren_floor_view', null)
  const view = editing ? 'plan' : (storedView || (isMobile ? 'list' : 'plan'))
  const hasStations = (stations || []).length > 0
  const live = useStationSummary(currentFloor?.name, hasStations)
  // open panel survives a reload (?panel=menu | reservations)
  const [panel, setPanelState] = useState(() => getUrlParam('panel'))
  const setPanel = (p) => { setPanelState(p); setUrlParams({ panel: p, ...(p === 'menu' ? {} : { menu: null, menu_tab: null }), ...(p === 'reservations' ? {} : { view: null }) }) }
  const menuOpen = panel === 'menu'
  const booking = panel === 'reservations'
  const setMenuOpen = (open) => setPanel(open ? 'menu' : null)
  const setBooking = (open) => setPanel(open ? 'reservations' : null)

  const handleTableSelect = (table) => {
    setCurrentTable(table)
  }

  const handleFloorClick = (e) => {
    // React bubbles events from portals (the order screen opened from a
    // table) up to here: only clicks on the plan itself deselect, and only
    // they may preventDefault (it would stop inputs from taking focus).
    if (!e.currentTarget.contains(e.target)) return
    e.stopPropagation()
    e.preventDefault()
    setCurrentTable(null)
  }

  const addTable = () => {
    callMethod(
      'Ren Room',
      currentRoom.name,
      'add_table',
      {
        freeze: false
      } 
    )
  }

  const addStation = () => {
    callMethod(
      'Ren Floor',
      currentFloor.name,
      'add_station',
      {
        freeze: false
      } 
    )
  }

  const handleRoomEdit = () => {
    MetaForm.edit('Ren Room', currentRoom.name, {
      title: __(`Update Room`),
      fields: ['description', 'menu'],
      fieldProperties: {
        menu: {
          get_query: () => ({
            filters: {
              company: frappe.defaults.get_user_default("company")
            }
          })
        }
      }
    });
  }

  // the room list is reloaded right away (the realtime event also updates other screens)
  const handleRoomDelete = () => {
    callMethod("Ren Room", currentRoom.name, "delete").then(() => loadObjects(), () => {})
  }

  const handleSelectBooking= () => {
    setBooking(true)
  }

  if (!currentFloor) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <EmptyState text="No Floor selected" icon={UtensilsCrossed} />
      </div>
    )
  }

  // only production centers on this floor for this person (a cook): they are the screen
  const productionOnly = !editing && !(rooms || []).length && hasStations
  const showDock = !isMobile && !productionOnly && (hasStations || (editing && can('station.create')))
  const showSheet = isMobile && !productionOnly && hasStations

  const tools = !editing && (
    <div className="flex items-center gap-1.5 shrink-0">
      <div className="flex h-10 rounded-lg border border-border overflow-hidden bg-card">
        <button
          title={__('Plan')}
          onClick={() => setView('plan')}
          className={`w-10 flex items-center justify-center ${view === 'plan' ? 'bg-foreground/15 text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
        ><MapIcon size={17} /></button>
        <button
          title={__('List')}
          onClick={() => setView('list')}
          className={`w-10 flex items-center justify-center border-l border-border ${view === 'list' ? 'bg-foreground/15 text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
        ><LayoutGrid size={17} /></button>
      </div>
      {!!REN?.access?.manage_reservations && <BookingButton onClick={handleSelectBooking}/>}
    </div>
  )

  return (
    <>
      {booking && <ReservationsBoard open={booking} onClose={() => setBooking(false)} />}
      <MenuManager open={menuOpen} onClose={() => setMenuOpen(false)} />
      <div className="flex-1 flex flex-col min-h-0 min-w-0">
        <div className="flex-1 flex min-h-0">
          {productionOnly ? (
            <ProductionHome stations={stations} live={live} />
          ) : (
            <div className="flex-1 flex flex-col bg-transparent relative min-h-0 min-w-0">
              {editing && (
                <div
                  className="flex items-center justify-between px-2 py-2 bg-transparent absolute top-0 left-0 right-0 z-10"
                >
                  <div className="flex items-center gap-2">
                    {currentRoom ? <AddTableButton onAdd={addTable} /> : null}
                  </div>
                  <div className="flex items-center gap-2">
                    {currentRoom ? (
                      <>
                        <EditRoomButton onClick={handleRoomEdit}/>
                        <DeleteRoomButton onClick={handleRoomDelete}/>
                      </>
                    ) : null}
                    <MenuButton onClick={() => setMenuOpen(true)}/>
                  </div>
                </div>
              )}

              {view === 'list' ? (
                currentRoom ? <TableList tables={tables || []} room={currentRoom} tools={tools} /> : <EmptyState text="No Rooms" icon={UtensilsCrossed} />
              ) : (
                <>
                  {tools && <div className="absolute top-2 right-2 z-10">{tools}</div>}
                  <div
                    className="flex-1 relative overflow-auto min-h-0"
                    onMouseDown={handleFloorClick}
                  >
                    <div className="absolute inset-0">
                      {currentRoom ? (
                        <>
                          {(tables || []).map(table => (
                            <Table key={table.name} table={{ ...table, room: currentRoom }} onSelect={handleTableSelect} />
                          ))}
                          {!tables?.length && (
                            <EmptyState text="No tables in this room" icon={UtensilsCrossed} />
                          )}
                        </>
                      ) : <EmptyState text="No Rooms" icon={UtensilsCrossed} />}
                    </div>
                  </div>
                </>
              )}
            </div>
          )}
          {showDock && <ProductionDock stations={stations || []} live={live} onAdd={addStation} />}
        </div>
        {showSheet && <ProductionSheet stations={stations} live={live} />}
      </div>
    </>
  )
}

function EmptyState({ text, icon: Icon }) {
  return (
    <div className="flex flex-col items-center justify-center w-full h-full gap-3">
      {Icon && <Icon className="w-12 h-12 text-muted-foreground/50" />}
      <span className="text-muted-foreground text-lg">{__(text)}</span>
    </div>
  )
}
