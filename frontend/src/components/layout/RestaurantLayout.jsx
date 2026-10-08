import { useEffect, useState } from 'react'
import { RoomsBar } from '../rooms/RoomsBar.jsx'
import { FloorMap } from '../floor/FloorMap.jsx'
import { FloorElevator } from './FloorElevator.jsx'
import { useIsMobile } from '@c/order/hooks/useIsMobile'

/**
 * The layout is position:fixed so it can use the whole screen, but it must
 * start after the Desk chrome: the v16 left sidebar (.body-sidebar, 50px
 * collapsed / wider expanded, hidden on mobile) and this page's head.
 * Both are measured live so expanding the sidebar or resizing reflows it.
 */
function measureDeskArea() {
  const root = document.getElementById('restaurant-root')
  const page = root?.closest('.page-container') || document
  const head = page.querySelector('.page-head')
  const sidebar = document.querySelector('.body-sidebar')

  const visible = (el) => el && el.offsetParent !== null && el.getBoundingClientRect().width > 0
  const left = visible(sidebar) ? Math.max(0, Math.round(sidebar.getBoundingClientRect().right)) : 0
  const top = visible(head) ? Math.max(0, Math.round(head.getBoundingClientRect().bottom)) : 50
  return { left, top }
}

function useDeskArea() {
  const [area, setArea] = useState(measureDeskArea)

  useEffect(() => {
    let frame = 0
    const update = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => {
        const next = measureDeskArea()
        setArea((prev) => (prev.left === next.left && prev.top === next.top ? prev : next))
      })
    }

    const observer = new ResizeObserver(update)
    const sidebar = document.querySelector('.body-sidebar')
    const head = document.getElementById('restaurant-root')
      ?.closest('.page-container')?.querySelector('.page-head')
    sidebar && observer.observe(sidebar)
    head && observer.observe(head)

    window.addEventListener('resize', update)
    sidebar?.addEventListener('transitionend', update)
    update()

    return () => {
      cancelAnimationFrame(frame)
      observer.disconnect()
      window.removeEventListener('resize', update)
      sidebar?.removeEventListener('transitionend', update)
    }
  }, [])

  return area
}

export default function RestaurantLayout() {
  const { left, top } = useDeskArea()
  // phones: the floor is picked from the top bar, the rail would eat the width
  const isMobile = useIsMobile()

  return (
    <div
      style={{
        position: "fixed",
        zIndex: 200,
        left,
        top,
        right: 0,
        bottom: 0,
      }}
    >
      <div className="absolute w-full h-full flex flex-col bg-background text-color">
        <RoomsBar />
        <div className="flex flex-row flex-1 min-h-0">
          {!isMobile && <FloorElevator />}
          <FloorMap />
        </div>
      </div>
    </div>
  )
}
