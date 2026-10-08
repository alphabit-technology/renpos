# Ren POS

Restaurant point of sale for ERPNext v16: floor plan, orders, kitchen and
dispatch stations, delivery and online ordering, all charged through ERPNext
POS invoices.

## Features

- **Floor plan**: floors, rooms and tables drawn on screen; the POS opens on
  the table and shows who serves it.
- **Orders**: items from the restaurant's menu, options and combos (sizes,
  sections, components sent to their own stations), hold and fire, split and
  move, guest notes, voids with a reason.
- **Ren Stations** (kitchen display): each station follows its own flow of
  statuses for its item groups, rooms or tables. A station can also wait for
  the whole order (expo / dispatch) and ask who delivers it.
- **Delivery**: zones by ZIP code that pick the branch, fee and minimum;
  phone orders from the call center.
- **Online ordering**: table QR and pickup / delivery pages for guests.
- **Staff**: Ren Staff says who works at each restaurant, with which Ren Role
  and on which floors, rooms, tables or stations. PIN login on shared
  terminals.
- **Charging**: the cashier's POS Profile (register opening, payment methods,
  discounts, price list) is used for the invoice; tips, card payments,
  loyalty points, receipts and the cash drawer.
- **Recipes**: a BOM per dish; ingredients leave stock at the register close,
  with a usage variance report.
- **Reservations**.

## Requirements

- Frappe / ERPNext v16

## Installation

```bash
bench get-app <repository url>
bench --site your-site install-app renpos
```

The POS is the **Ren POS** page (`/app/ren-pos`); setup is in the
**Restaurant** workspace.

### Sites that ran the old app (`restaurant_management`)

```bash
bench get-app <repository url>        # puts renpos in apps/
# sites/apps.txt: replace restaurant_management with renpos
bench --site your-site renpos-migrate-site
bench --site your-site migrate
```

## Frontend

The POS and the guest pages are React apps in `frontend/` (Vite + Tailwind).
The build goes to `renpos/public/dist`:

```bash
cd frontend
npm install
npm run build
```

## Tests

```bash
bench --site your-test-site run-tests --module renpos.tests.test_order_flow
```

## License

GNU General Public License v3, see [license.txt](license.txt).
