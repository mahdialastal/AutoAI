# AutoShorts web UI

React + Vite + Tailwind 4 frontend for the FastAPI backend.

## Development

Two processes: the Python API on `:8000` and Vite on `:5173`.

```bash
# terminal 1 — backend
python server.py

# terminal 2 — frontend
cd web
npm install
npm run dev
```

Open http://localhost:5173. Vite proxies `/api/*` to the FastAPI server, so the same code runs unchanged in production.

## Production

```bash
cd web
npm run build
# -> web/dist/

# Back in the repo root:
python server.py
# FastAPI detects web/dist/ and serves it at /
# Open http://localhost:8000
```

## Stack

- **React 19** + TypeScript
- **Vite 6** for dev server + bundler
- **Tailwind 4** via the `@tailwindcss/vite` plugin (no postcss config)
- No external UI library — small set of hand-rolled primitives in `src/components/ui.tsx`

## Layout

```
web/
  index.html
  vite.config.ts
  src/
    main.tsx                # bootstrap
    App.tsx                 # top-level phase state (idle → running → done)
    index.css               # Tailwind + scrollbar styling
    api/client.ts           # typed fetch wrappers + SSE subscriber
    components/
      ui.tsx                # Button, Input, Select, Card, ProgressBar, Badge
      SourceForm.tsx        # URL / upload + settings + Generate
      ProgressCard.tsx      # SSE-driven stage display
      ShortCard.tsx         # single short: player + transcript + (S3) trim/publish
      ShortsGrid.tsx        # grid of ShortCards
    lib/utils.ts            # cn() classname helper
```

## What's next (S3)

- Trim & re-render on a short (`POST /api/shorts/.../trim` — to be built)
- Publish dispatcher (calls existing `POST /api/publish`)
- History / run picker in a left rail
- Credentials UI (drop tokens in without editing JSON by hand)
