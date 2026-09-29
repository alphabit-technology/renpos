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
      <div className="absolute w-full h-full flex flex-row">
        <FloorElevator />
        <div className="flex flex-col h-full w-full bg-background text-color">
          <div className="flex items-stretch shrink-0 h-12 border border-slate-500/30">
            <RoomsBar />
          </div>
          <RoomsBar />
          <FloorMap />
        </div>
      </div>
    </div>
  )
}