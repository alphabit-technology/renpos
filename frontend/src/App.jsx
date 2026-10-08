import { RestaurantProvider } from './context/RestaurantContext'
import { FloorsProvider } from './context/FloorsContext'
import { RoomsProvider } from './context/RoomsContext'
import RestaurantLayout from './components/layout/RestaurantLayout'
import { useState, useEffect } from 'react'
import GuestOrderAlerts from './components/order/GuestOrderAlerts'
import './index.css'

function App({posWrapper}) {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    requestAnimationFrame(() => setReady(true));
  }, []);


  return (
    <div className={`restaurant-app ${ready ? 'visible' : ''}`}>
    <RestaurantProvider posWrapper={posWrapper}>
      <FloorsProvider>
        <RoomsProvider>
          <RestaurantLayout />
          <GuestOrderAlerts />
        </RoomsProvider>
      </FloorsProvider>
    </RestaurantProvider>
    </div>
  )
}

export default App