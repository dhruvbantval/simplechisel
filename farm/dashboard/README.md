# AutoExperiment Farm dashboard

The React front end. It reads the farm's record store and drives the backend at
[../webapp](../webapp), so it needs that backend running to do anything beyond
browsing an uploaded run.

Requires [node.js](https://nodejs.org/en).

```bash
npm install     # once
npm run dev     # Vite dev server on :5173, proxying /api to :8000
npm run build   # production build into dist/
```

Normally you don't run these directly — [../webapp/serve.sh](../webapp/serve.sh)
builds the dashboard and serves it together with the API from one origin, and
[../webapp/dev.sh](../webapp/dev.sh) runs both in hot-reload mode.

## Layout

```
src/
  App.jsx              shell: view state, providers, data wiring
  components/
    layout/            sidebar + top bar
    dashboard/         one component per view
    primitives/        Section, Badge, Icon, Toast, LogPane, ...
  data/
    api.js             backend client
    jobs.jsx           background job tracking (survives navigation)
    records.js         cross-domain derivations over /api/records
    trend.js           regression trend series
    metrics.js         cosim-only run JSON derivations
public/                favicons, logo, bundled sample runs
```

Run JSON uploaded by hand is validated against
[docs/json-schema.md](docs/json-schema.md).
