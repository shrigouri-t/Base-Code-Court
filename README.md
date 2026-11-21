# CodeCourt

CodeCourt analyzes public GitHub repositories and scores contributor contributions with
transparent work, survival, ownership, review, issue, and consistency signals.

The backend provides repository ingestion, Git analysis, GitHub activity collection,
scoring, persistence, background jobs, REST endpoints, and PDF/JSON report export.
The frontend can be developed separately against the API.

## Backend setup

```powershell
cd backend
py -3.11 -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs.

## Frontend setup

With the backend running, open a second terminal:

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

Open the Vite URL (usually http://localhost:5173). The frontend defaults to the
backend at http://127.0.0.1:8000; set `VITE_API_BASE_URL` in `frontend/.env` to
change it. The CodeCourt dashboard starts an analysis for a public GitHub
repository, tracks its progress, displays contributor rankings and analysis
details, and downloads the PDF report. See [frontend/README.md](./frontend/README.md)
for the UI workflow and validation commands.

## Validation

```powershell
cd backend
python -m pytest -q
```
