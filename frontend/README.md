# CodeCourt frontend

CodeCourt is a responsive GitHub contribution analysis dashboard built with React
and Vite. Its palette pairs a deep slate/indigo workspace (`#121c2c`) with mint
accents (`#72dfb7`), soft neutrals, and restrained gold highlights.

## Run locally

Start the backend first (see the repository's main README), then from this
directory:

```powershell
npm install
Copy-Item .env.example .env
npm run dev
```

By default, the UI calls `http://127.0.0.1:8000`. Set
`VITE_API_BASE_URL` in `.env` if the backend is hosted elsewhere. The backend
must allow the frontend's origin through CORS.

## What it does

- Accepts a public GitHub URL or `owner/repository` and starts `POST /analyze`.
- Polls `GET /analyses/{analysis_id}` until analysis succeeds or fails.
- Shows the contributor ranking, score, commit and survival data, weekly
  contribution timeline, directory ownership, and anomaly notes.
- Downloads the completed report from `GET /reports/{analysis_id}/pdf`.
- Displays recent analysis IDs from `GET /analyses`.

The frontend does not require GitHub OAuth. Repository analysis and report
requests go directly to the CodeCourt backend API.

## Checks

```powershell
npm run lint
npm run build
```
