import { memo } from "react";
import { ItemTree } from "@c/items";
//import { useRestaurant } from '@/context/RestaurantContext.jsx'
import { useRooms} from "@/context/RoomsContext"

export const ItemCatalog = memo(function ItemCatalog({ onItemClick }) {
  //const { RM } = useRestaurant();
  const {activeMenu} = useRooms();
  //const {restaurant} = RM

  //console.log(["acrtiveMenu", activeMenu])

  return (
    <main className="flex-1 flex flex-col min-w-0 min-h-0">
      <ItemTree
        enabled={true}
        className="flex-1"
        onItemClick={onItemClick}
        menuName={activeMenu || "__not_assigned_menu__"}
        menuMode={false}
        showOrderQty={true}
      />
    </main>
  );
});