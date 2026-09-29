import { useRestaurant } from '../../context/RestaurantContext.jsx'
import { Table } from '../objects/Table.jsx'
import {Station } from '../objects/Station.jsx'
import {useRooms} from "@/context/RoomsContext.jsx"
import {useFloors} from "@/context/FloorsContext.jsx"
import Booking from "@c/booking/Booking"

import {
  AddTableButton,
  AddProductionCenterButton,
  EditRoomButton,
  DeleteRoomButton,
  MenuButton,
  BookingButton
} from './FloorActions.jsx'

import { UtensilsCrossed } from 'lucide-react'
import { useState, useEffect } from 'react'
import {MenuManager} from "../menu/MenuManager.jsx"

export function FloorMap() {
  const { setCurrentTable, editing, callMethod } = useRestaurant()
  const { currentFloor, tables, stations, floorsLoading } = useFloors()
  const { currentRoom, roomsLoading } = useRooms()
  const [menuOpen, setMenuOpen] = useState(false)
  const [booking, setBooking] = useState(false)

  const handleTableSelect = (table) => {
    setCurrentTable(table)
  }

  const handleFloorClick = (e) => {
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

  const handleRoomDelete = () => {
    callMethod("Ren Room", currentRoom.name, "delete")
  }

  const handleSelectBooking= () => {
    setBooking(true)
  }

  if (floorsLoading || roomsLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <span className="text-muted-foreground text-sm animate-pulse">Loading...</span>
      </div>
    )
  }

  if (!currentFloor) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <EmptyState text="No Floor selected" icon={UtensilsCrossed} />
      </div>
    )
  }

  return (
    <>
      {booking && <Booking open={booking} onClose={() => setBooking(false)} />}
      <MenuManager open={menuOpen} onClose={() => setMenuOpen(false)} />
      <div className="flex-1 flex flex-col bg-transparent relative min-h-0">
        {editing && (
          <div 
            className="flex items-center justify-between px-2 py-2 bg-transparent absolute top-0 left-0 right-0 z-10"
          >
            <div className="flex items-center gap-2">
              {currentRoom ? <AddTableButton onAdd={addTable} /> : null}
              <AddProductionCenterButton onAdd={addStation} />
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

        {!editing && (
          <div className="absolute top-2 right-2 z-10">
            <BookingButton onClick={handleSelectBooking}/>
          </div>
        )}

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
                {(stations || []).map(station => (
                  <Station key={station.name} station={{ ...station, room: currentRoom }} onSelect={handleTableSelect} />
                ))}
                {!tables?.length && !stations?.length && (
                  <EmptyState text="No tables in this room" icon={UtensilsCrossed} />
                )}
              </>
            ) : null}
          </div>
        </div>
      </div>
    </>
  )
}

function EmptyState({ text, icon: Icon }) {
  return (
    <div className="flex flex-col items-center justify-center w-full h-full gap-3">
      {Icon && <Icon className="w-12 h-12 text-muted-foreground/50" />}
      <span className="text-muted-foreground text-lg">{text}</span>
    </div>
  )
}