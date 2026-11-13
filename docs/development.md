# Developing on two computers

Supabase is the shared source of truth. The office laptop and the personal laptop run the same Git commit against the same development project. Neither computer has the database, the file store, or the user directory.

What moves with Git:

- Application source
- Alembic migrations in `backend/migrations`
- `.env.example` and `.env.production.example`

What you copy by hand into untracked env files, using the same values on both computers:

- `backend/.env`
- `frontend/.env.local`

What each computer creates for itself and never commits:

- `backend/.venv`
- `frontend/node_modules`
- `.next`

Uploaded documents go to the private Supabase Storage bucket `documents`. They are not stored in the repository or on the laptop disk.

## Tools to install once per computer

- Git
- Node.js 20 or newer
- Python 3.12 or newer

Do not install Postgres locally. Docker is not part of this setup.

## One-time Supabase setup

Do this once, in the shared development project. Do not repeat it on the second computer, and do not delete the project when changing machines.

1. Create a Supabase project for development. Use a different project later for production.
2. In Authentication → URL configuration, allow `http://localhost:3000` and `http://localhost:3000/reset-password`.
3. In Authentication → Providers → Email, keep email confirmation on.
4. In Storage, create a private bucket named `documents`.
5. Copy the session-pooler connection string from Connect. Change the scheme to `postgresql+psycopg://`. Do not use the direct `db.<ref>.supabase.co` host on the free plan; that host is IPv6-only.
6. Copy the project URL, the anon key, and the service role key. The anon key is safe for the frontend. The service role key stays in `backend/.env` only.

`vector` is created by the first migration. You do not need a local pgvector install.

## Clone and run on a new computer

From the directory where you keep projects:

```powershell
git clone https://github.com/YOUR_USER/VansoraAI.git
cd VansoraAI
```

Frontend:

```powershell
cd frontend
copy .env.example .env.local
npm install
```

Edit `frontend/.env.local` with the shared project URL and anon key. `NEXT_PUBLIC_API_URL` stays `http://localhost:8000` while the API runs on this computer.

Backend, from the repository root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env
```

Edit `backend/.env` with the same `DATABASE_URL`, `SUPABASE_URL`, and `SUPABASE_SERVICE_ROLE_KEY` you use on the other computer. Set `SECRET_KEY` to the same development value so you do not have to think about which laptop issued a token. Supabase issues the session tokens; this secret is for the app, not for Supabase Auth.

Apply migrations without touching existing rows:

```powershell
.\.venv\Scripts\python -m alembic upgrade head
```

If the output says the database is already at head, stop. That is the correct result on the second computer. Do not run `alembic downgrade`. Downgrade is refused unless `ALLOW_SCHEMA_DESTRUCT=yes`, and that variable must not be set for the shared project. Do not drop the schema, and do not create a new Supabase project to replace the one you already use.

Start the API:

```powershell
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

Start the site, from `frontend`:

```powershell
npm run dev
```

Open http://localhost:3000. Sign in with the Supabase account you created on the other computer. Organizations and later documents are already in the project.

The worker is a second process, only when a later phase enqueues jobs:

```powershell
cd backend
.\.venv\Scripts\python -m app.workers
```

## Continue on the other computer

```powershell
cd VansoraAI
git pull
cd frontend
npm install
cd ..\backend
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m alembic upgrade head
```

`npm install` and `pip install` pick up dependency changes. `alembic upgrade head` applies only new migration files. Then start Uvicorn and `npm run dev` as above. Your env files are already on that computer; do not replace them with empty examples.

## Tests

Frontend tests do not need a database:

```powershell
cd frontend
npm test
```

Backend tests are skipped until `TEST_DATABASE_URL` points at a **second** Supabase project used only for pytest. They migrate that database and then truncate it. The test run stops if that URL is the same host and database name as `DATABASE_URL` in `backend/.env`, and it stops if the URL points at localhost.

```powershell
cd backend
$env:TEST_DATABASE_URL = "postgresql+psycopg://..."
.\.venv\Scripts\python -m pytest
```

Do not export `TEST_DATABASE_URL` as the development database.

## Push changes

```powershell
cd VansoraAI
git status
git add .
git commit -m "Describe why the change was made"
git push
```

Before you add files, confirm `git status` does not list `backend/.env`, `frontend/.env.local`, or any file with a service role key, database password, or anon key. Those names are gitignored. If a secret was ever committed, rotate it in the Supabase dashboard.

## Production configuration

Production uses `backend/.env.production.example` and `frontend/.env.production.example` as the checklist. Put the real values in Render and Vercel, not in Git. Use a separate Supabase project from development when you deploy. See [deployment.md](deployment.md).
