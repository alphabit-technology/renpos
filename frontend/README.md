# Ren POS frontend

React apps loaded by the Frappe site:

- `src/main.jsx`: the POS (Desk page `ren-pos`), built to `../renpos/public/dist/js/restaurant.js`
- `src/guest/`: the guest ordering pages (`/order`), built with `--mode guest` to `dist/js/guest.js`

```bash
npm install
npm run build      # both bundles
npm run dev        # Vite dev server
npm run lint
```
