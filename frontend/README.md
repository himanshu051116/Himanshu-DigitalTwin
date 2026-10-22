# Optional Next.js interface

This folder contains an **additional** React/TypeScript dashboard. It is **not** the default submission demonstrator and does not replace the guided synthetic six-chapter experience served from FastAPI.

- Framework: Next.js 16.0.0, React 19.2.0, TypeScript 5.9.x.
- API integration: `frontend/app/page.tsx` connects to the FastAPI backend through `NEXT_PUBLIC_API_BASE`, defaulting to `http://localhost:8000`.
- Backend CORS in `backend/app/main.py` is configured for local development origins on port 3000.
- Sensor-gap handling: missing readings and unavailable excursion-risk output must render as unavailable or **withheld**, never as a 0% risk.

## Local development

Start the backend from the repository root:

```bash
python -m pip install -r backend/requirements.txt
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. The FastAPI-served judge dashboard remains available at `http://localhost:8000`.

Run `npx tsc --noEmit` for type checking or `npm run build` to test a frontend build. No hosted deployment or clinical-model integration is implied. The repository does not currently ship a frontend npm lockfile; for reproducible production dependency resolution, generate and commit one in a controlled environment.

[Root README](../README.md) · [API architecture](../docs/ARCHITECTURE_AND_MODELS.md)
