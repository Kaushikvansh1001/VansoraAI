# VansoraAI

Intelligence. Automation. Evolution.

VansoraAI is a multi-tenant business intelligence platform. The foundation is Supabase Auth, organizations, and a dashboard whose numbers come from the shared Supabase database. Knowledge accepts a text or PDF upload and answers questions from that file. The data analyst and workflows come later.

Both computers use one Supabase project. Setup steps for a new laptop are in [DEVELOPMENT.md](DEVELOPMENT.md) and [docs/development.md](docs/development.md). Deployment is in [docs/deployment.md](docs/deployment.md).

## Run

```powershell
cd backend
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

```powershell
cd frontend
npm run dev
```

The API reads `backend/.env`. The site reads `frontend/.env.local`. Copy those from the example files. Do not commit them.

`alembic upgrade head` is the only migration command to use on the shared database.

## Layout

```text
frontend/     Next.js, deployed on Vercel
backend/      FastAPI, deployed on Render's Python runtime
docs/         Development and deployment notes
```

The browser talks to Supabase Auth directly. Every organization record goes through the API with the Supabase access token. Uploaded files are stored in the private `documents` bucket, not on the laptop.

Organization admins can open **AI providers** to see whether Gemini, Groq, and Ollama are configured, then send a test prompt. Usage totals come from `ai_usage_logs`. Provider setup is described in [docs/ai.md](docs/ai.md).
