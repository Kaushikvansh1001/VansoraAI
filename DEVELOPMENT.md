# Development

Full notes, including the two-computer workflow, are in [docs/development.md](docs/development.md). Deployment is in [docs/deployment.md](docs/deployment.md). Provider keys are in [docs/ai.md](docs/ai.md).

## Versions

- Windows
- Git
- Node.js 20 or newer
- Python 3.12 or newer. This computer may use 3.14. Render uses 3.12.8.

Do not install PostgreSQL. The shared database and the `documents` bucket are in Supabase.

## First time on a computer

```powershell
git clone https://github.com/YOUR_USER/VansoraAI.git
cd VansoraAI
```

```powershell
cd frontend
copy .env.local.example .env.local
npm install
```

```powershell
cd ..\backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env
```

Fill `frontend/.env.local` and `backend/.env` with the same Supabase values used on the other computer. Leave an AI key blank until you have it.

```powershell
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

From `frontend`:

```powershell
npm run dev
```

Open http://localhost:3000.

`alembic upgrade head` is the only migration command for the shared project. If it reports that the database is already at head, stop. Do not downgrade, drop, or recreate the Supabase project.

## After pulling new code

```powershell
git pull
cd frontend
npm install
cd ..\backend
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m alembic upgrade head
```

Restart Uvicorn after any change to `backend/.env`. Saving the file does not reload keys into the running API.

## Do not commit

`backend/.env`, `frontend/.env.local`, service-role keys, database passwords, and provider keys. Example files are the only env files that belong in Git.
