import { useMemo } from 'react'
import { can, checkPermission, hasRole, canRead, canWrite, canCreate, canDelete } from './permissions'

/**
 * Hook to check permissions reactively
 * 
 * Usage:
 *   const { allowed, canEdit, canRemove } = usePermission('table')
 *   const { allowed } = usePermission({ doctype: 'REN Order', perm: 'create' })
 */
export function usePermission(nameOrRule) {
  return useMemo(() => {
    if (typeof nameOrRule === 'string') {
      const base = nameOrRule;
      return {
        allowed: can(base),
        canEdit: can(`${base}.edit`),
        canCreate: can(`${base}.create`),
        canDelete: can(`${base}.delete`),
        canWrite: can(`${base}.write`),
      };
    }

    return {
      allowed: checkPermission(nameOrRule),
    };
  }, [nameOrRule]);
}

/**
 * Hook to check multiple permissions at once
 * 
 * Usage:
 *   const perms = usePermissions(['table', 'order', 'menu'])
 *   perms.table.allowed // true/false
 *   perms.order.canEdit // true/false
 */
export function usePermissions(names) {
  return useMemo(() => {
    const result = {};
    for (const name of names) {
      result[name] = {
        allowed: can(name),
        canEdit: can(`${name}.edit`),
        canCreate: can(`${name}.create`),
        canDelete: can(`${name}.delete`),
        canWrite: can(`${name}.write`),
      };
    }
    return result;
  }, [names.join(',')]);
}

/**
 * Hook for role-based checks
 * 
 * Usage:
 *   const isManager = useRole('Restaurant Manager')
 *   const isStaff = useRole(['Restaurant Manager', 'Restaurant Waiter'])
 */
export function useRole(role) {
  return useMemo(() => hasRole(role), [role]);
}