import { RoomsBar } from '../rooms/RoomsBar.jsx'
import { FloorMap } from '../floor/FloorMap.jsx'
import { FloorElevator } from './FloorElevator.jsx'

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
        <RoomsBar />
        <div className="flex flex-row flex-1 min-h-0">
          <FloorElevator />
          <FloorMap />
        </div>
      </div>
    </div>
  )
}