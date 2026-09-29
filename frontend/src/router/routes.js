import { lazy } from 'react'

/**
 * Route config for the restaurant module
 * Each route declares its permission requirement
 * 
 * permission: string key from PERMISSIONS map, or a rule object
 * lazy: enables code splitting per route
 */

// Lazy-loaded views
const Layout = lazy(() => import('@/views/Layout'));
const FloorView = lazy(() => import('@/views/FloorView'));
const RoomView = lazy(() => import('@/views/RoomView'));
const TableView = lazy(() => import('@/views/TableView'));
const OrderManage = lazy(() => import('@/views/OrderManage'));
const MenuManage = lazy(() => import('@/views/MenuManage'));
const Station = lazy(() => import('@/views/Station'));

const routes = [
  {
    path: '/',
    element: Layout,
    permission: 'restaurant',
    children: [
      {
        index: true,
        element: FloorView,
        permission: 'floor',
      },
      {
        path: 'floor/:floorId',
        element: FloorView,
        permission: 'floor',
      },
      {
        path: 'floor/:floorId/room/:roomId',
        element: RoomView,
        permission: 'room',
      },
      {
        path: 'table/:tableId',
        element: TableView,
        permission: 'table',
      },
      {
        path: 'table/:tableId/order',
        element: OrderManage,
        permission: 'order',
      },
      {
        path: 'table/:tableId/order/:orderId',
        element: OrderManage,
        permission: 'order',
      },
    ],
  },
  {
    path: '/menu',
    element: MenuManage,
    permission: 'menu',
  },
  {
    path: '/station',
    element: Station,
    permission: 'station',
  },
];

export default routes;