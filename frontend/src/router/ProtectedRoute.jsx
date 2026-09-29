import { Navigate, useLocation } from 'react-router-dom'
import { can, checkPermission } from './permissions'

/**
 * Route guard that checks permissions before rendering
 * 
 * Usage in routes:
 *   <Route path="/table/:id" element={
 *     <ProtectedRoute permission="table" fallback="/"><TableView /></ProtectedRoute>
 *   } />
 * 
 *   <Route path="/menu" element={
 *     <ProtectedRoute permission={{ roles: ['Restaurant Manager'] }} fallback="/">
 *       <MenuManage />
 *     </ProtectedRoute>
 *   } />
 */
function ProtectedRoute({
  children,
  permission,
  fallback = '/',
  unauthorized: UnauthorizedComponent,
}) {
  const location = useLocation();

  const allowed = typeof permission === 'string'
    ? can(permission)
    : checkPermission(permission);

  if (!allowed) {
    if (UnauthorizedComponent) {
      return <UnauthorizedComponent />;
    }

    return <Navigate to={fallback} state={{ from: location, reason: 'unauthorized' }} replace />;
  }

  return children;
}

export default ProtectedRoute;