import { Suspense } from 'react'
import { MemoryRouter, Routes, Route, Navigate } from 'react-router-dom'
import ProtectedRoute from './ProtectedRoute'
import routeConfig from './routes'

function Unauthorized() {
  return (
    <div className="flex items-center justify-center h-full text-[var(--text-muted,#888)]">
      <div className="text-center">
        <p className="text-lg font-semibold">{__('Access Denied')}</p>
        <p className="text-sm mt-1">{__('You do not have permission to access this page.')}</p>
      </div>
    </div>
  );
}

function Loading() {
  return (
    <div className="flex items-center justify-center h-full text-[var(--text-muted,#888)]">
      {__('Loading...')}
    </div>
  );
}

function buildRoutes(routes) {
  return routes.map((route, index) => {
    const Element = route.element;

    const wrapped = (
      <ProtectedRoute
        permission={route.permission}
        unauthorized={Unauthorized}
      >
        <Element />
      </ProtectedRoute>
    );

    if (route.children) {
      return (
        <Route key={route.path || index} path={route.path} element={wrapped}>
          {buildRoutes(route.children)}
        </Route>
      );
    }

    return (
      <Route
        key={route.path || index}
        path={route.path}
        index={route.index}
        element={wrapped}
      />
    );
  });
}

function RestaurantRouter() {
  return (
    <MemoryRouter>
      <Suspense fallback={<Loading />}>
        <Routes>
          {buildRoutes(routeConfig)}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </MemoryRouter>
  );
}

export default RestaurantRouter;