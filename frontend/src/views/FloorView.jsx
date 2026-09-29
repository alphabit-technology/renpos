import { useRestaurant } from '@/context/RestaurantContext.jsx'
import { Table } from '@c/objects/Table.jsx'
import {Station } from '@c/objects/Station.jsx'
import { useTables } from '@/hooks/useTables'
import {useRooms} from "@/context/RoomsContext.jsx"
import {useFloors} from "@/context/FloorsContext.jsx"
import {
  AddTableButton,
  AddProductionCenterButton,
  EditRoomButton,
  DeleteRoomButton,
  MenuButton,
  CheckInButton
} from '@c/floor/FloorActions.jsx'
import { UtensilsCrossed } from 'lucide-react'
import { useState } from 'react'
import {MenuManage} from "@c/floor/MenuManage.jsx"

export function FloorView() {
  const {
    setCurrentTable,
    editing,
    callMethod
  } = useRestaurant()

  const { currentFloor } = useFloors()
  const { currentRoom, stations } = useRooms();
  const [menuOpen, setMenuOpen] = useState(false);

  const { tables } = useTables([])

  const handleTableSelect = (table) => {
    setCurrentTable(table)
  }

  const handleFloorClick = (e) => {
    e.stopPropagation()
    e.preventDefault()
    setCurrentTable(null)
  }

  const handleDelete = (tableName) => {
    // handled via realtime, but could force refresh here
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
    DeskForm.open({
      doc_name: currentRoom.name,
      form_name: "Restaurant Room",
      title: __(`Update Room`),
      callback: (self) => self.hide()
    });
  }

  const handleRoomDelete = () => {
    callMethod("Ren Room", currentRoom.name, "delete")
  }

  if (!currentFloor) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <span className="text-muted-foreground text-lg">No floor selected</span>
      </div>
    )
  }

  return (
    <>
    <MenuManage open={menuOpen} onClose={() => setMenuOpen(false)} />
    <div className="flex-1 flex flex-col bg-transparent relative min-h-0">
      {editing && currentRoom && (
        <div 
          className="flex items-center justify-between px-2 py-2 bg-transparent absolute top-0 left-0 right-0 z-10"
        >
          <div className="flex items-center gap-2">
            <AddTableButton onAdd={addTable} />
            <AddProductionCenterButton onAdd={addStation} />
          </div>
          <div className="flex items-center gap-2">
            <EditRoomButton onClick={handleRoomEdit}/>
            <DeleteRoomButton onClick={handleRoomDelete}/>
          </div>
        </div>
      )}

      {!editing && (
        <div className="absolute top-2 right-2 z-10">
          <CheckInButton />
        </div>
      )}

      <div
        className="flex-1 relative overflow-auto min-h-0"
        onMouseDown={handleFloorClick}
      >
        <div className="absolute inset-0">
          {!currentRoom ? (
            <div className="flex flex-col items-center justify-center w-full h-full gap-3">
              <span className="text-muted-foreground text-lg">No rooms in this floor</span>
            </div>
          ) : ((!tables || tables.length === 0) && (!stations || stations.length === 0)) ? (
            <div className="flex flex-col items-center justify-center w-full h-full gap-3">
              <UtensilsCrossed className="w-12 h-12 text-muted-foreground/50" />
              <span className="text-muted-foreground text-lg">Empty Room...</span>
            </div>
          ) : (
            <>
              {(tables || []).map((table) => (
                <Table
                  key={table.name}
                  table={{ ...table, room: currentRoom }}
                  onSelect={handleTableSelect}
                  onDelete={handleDelete}
                />
              ))}
              {(stations || []).map((station) => (
                <Station
                  key={station.name}
                  station={{ ...station, room: currentRoom }}
                  onSelect={handleTableSelect}
                  onDelete={handleDelete}
                />
              ))}
            </>
          )}
        </div>
      </div>
    </div>
    </>
  )
}