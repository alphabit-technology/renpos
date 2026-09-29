import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'

function mountApp(container, posWrapper) {
  const root = ReactDOM.createRoot(container)
  root.render(
    <React.StrictMode>
      <App posWrapper={posWrapper}/>
    </React.StrictMode>
  )
  return root
}

if (import.meta.env.DEV) {
  const container = document.getElementById('restaurant-root')
  if (container) {
    mountApp(container)
  }
}

window.initRestaurantApp = mountApp