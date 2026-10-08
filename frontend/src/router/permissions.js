/**
 * Restaurant permission helper
 * Uses the permissions the server sends with init_restaurant
 */

let _ren = null;

export function initPermissions(ren) {
  _ren = ren;
}

// ─── Map PERMISSIONS doctype → REN.permissions key ────────────

const PERM_KEY_MAP = {
  'Ren Floor':      'ren_floor',
  'Ren Room':       'ren_room',
  'Ren Table':      'ren_table',
  'Ren Station':    'ren_station',
  'Ren Order':    'order',
  'Sales Invoice':  'invoice',
};

// ─── Role checks ─────────────────────────────────────────────

export function hasRole(role) {
  if (Array.isArray(role)) {
    return role.some(r => frappe.user_roles.includes(r));
  }
  return frappe.user_roles.includes(role);
}

export function isAdmin() {
  return hasRole(['System Manager', 'Administrator']);
}

// ─── Core check ──────────────────────────────────────────────

export function checkPermission(rule) {
  if (!rule) return true;

  const { doctype, perm, roles, custom, all } = rule;
  const checks = [];

  if (doctype && perm) {
    // Permissions come from the server keyed by doctype (init_restaurant).
    return _ren?.permissions?.[doctype]?.[perm]
  }

  if (roles) {
    checks.push(hasRole(roles));
  }

  if (typeof custom === 'function') {
    checks.push(custom());
  }

  if (checks.length === 0) return true;

  return all ? checks.every(Boolean) : checks.some(Boolean);
}

// ─── Permission map ──────────────────────────────────────────

export const PERMISSIONS = {
  'floor':           { doctype: 'Ren Floor', perm: 'read' },
  'floor.write':     { doctype: 'Ren Floor', perm: 'write' },
  'floor.create':    { doctype: 'Ren Floor', perm: 'create' },

  'room':            { doctype: 'Ren Room', perm: 'read' },
  'room.write':      { doctype: 'Ren Room', perm: 'write' },
  'room.create':     { doctype: 'Ren Room', perm: 'create' },
  'room.delete':     { doctype: 'Ren Room', perm: 'delete' },

  'table':           { doctype: 'Ren Table', perm: 'read' },
  'table.write':     { doctype: 'Ren Table', perm: 'write' },
  'table.create':    { doctype: 'Ren Table', perm: 'create' },
  'table.delete':    { doctype: 'Ren Table', perm: 'delete' },

  'station':         { doctype: 'Ren Station', perm: 'read' },
  'station.write':   { doctype: 'Ren Station', perm: 'write' },
  'station.create':  { doctype: 'Ren Station', perm: 'create' },
  'station.delete':  { doctype: 'Ren Station', perm: 'delete' },

  'order':           { doctype: 'Ren Order', perm: 'read' },
  'order.create':    { doctype: 'Ren Order', perm: 'create' },
  'order.write':     { doctype: 'Ren Order', perm: 'write' },

  'menu':           { doctype: 'Ren Menu', perm: 'read' },
  'menu.create':    { doctype: 'Ren Menu', perm: 'create' },
  'menu.write':     { doctype: 'Ren Menu', perm: 'write' }
};

export function can(name) {
  const rule = PERMISSIONS[name];
  if (!rule) {
    console.warn(`Unknown permission: "${name}"`);
    return false;
  }
  return checkPermission(rule);
}

export const generalCustomAccess = () => {
  const docs = ["room", "table", "station"];
  const permissions = ["create", "write", "delete"];
  for (const doc of docs) {
    for (const perm of permissions) {
      const key = `${doc}.${perm}`;
      if (PERMISSIONS[key] && can(key)) {
        return true;
      }
    }
  }
  return false;
};

