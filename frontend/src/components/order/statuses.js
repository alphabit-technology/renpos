// Which order line statuses the waiter can still edit. The server sends the
// list with the POS data (Ren Order Status "Allows to edit Item").
let editable = new Set(["Pending", "Attending"]);

export function setEditableStatuses(list) {
  if (Array.isArray(list) && list.length) editable = new Set(list);
}

export function isEditable(status) {
  return !status || editable.has(status);
}
