import { RoomsBar } from '@c/rooms/RoomsBar.jsx'
import { FloorMap } from '@c/floor/FloorMap.jsx'
import { FloorElevator } from '@c/layout/FloorElevator.jsx'

export default function RestaurantLayout() {
  return (
    <div
      style={{
        position: "fixed",
        zIndex: 200,
        left: 0,
        top: "50px",
        width: "100%",
        height: "calc(100% - 50px)"
      }}
    >
      <div className="absolute w-full h-full flex flex-col bg-background text-color">
        <div className="flex items-stretch shrink-0 h-12 border-b border-border">
          <RoomsBar />
        </div>
        <div className="flex flex-row flex-1 min-h-0">
          <FloorElevator />
          <FloorMap />
        </div>
      </div>
    </div>
  )
}