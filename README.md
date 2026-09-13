# USQL Client Backend

FastAPI backend for SSO (Sign in with Google) used by the Universal SQL Client
desktop app. Runs independently — start it with its own virtual environment.

## Setup

```bash
# 1. Clone / navigate to the project root
git clone https://github.com/mitayan0/USQL-Client-Backend.git
cd USQL-Client-Backend

# 2. Create and activate the virtual environment
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS / Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
copy .env.example .env            # Windows
# cp .env.example .env            # macOS / Linux
# → open .env and fill in DATABASE_URL + Google OAuth credentials + JWT_SECRET

# 5. Create the database once (name must match DATABASE_URL in .env)
createdb -U postgres usqlc
# or: psql -U postgres -c "CREATE DATABASE usqlc;"

# 6. Create the tables
alembic upgrade head
```

## Running the App

```bash
# Activate the virtual environment first (if not already active)
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS / Linux

# Start the development server with hot-reload
uvicorn app.main:app --reload --port 8000
```

- **API docs (Swagger UI):** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
- **Health check:** http://localhost:8000/health

## Database Migrations (Alembic)

The `DATABASE_URL` is read from `.env` automatically by `migrations/env.py`.
All commands below must be run from the project root with the virtual environment active.

```bash
# Apply all pending migrations (bring the DB up to the latest revision)
alembic upgrade head

# Roll back the most recent migration
alembic downgrade -1

# Roll back all migrations (empty database schema)
alembic downgrade base

# Upgrade / downgrade to a specific revision
alembic upgrade  <revision_id>
alembic downgrade <revision_id>

# Auto-generate a new migration from model changes
alembic revision --autogenerate -m "describe your change here"

# Show the current revision applied to the database
alembic current

# Show the full migration history
alembic history --verbose

# Show pending (unapplied) migrations
alembic history -r current:head
```

> **Note:** After adding or changing SQLAlchemy models, always run
> `alembic revision --autogenerate` and review the generated script before
> applying it with `alembic upgrade head`.

## Google OAuth Setup

1. Create an OAuth Client ID (Web application) in
   https://console.cloud.google.com/apis/credentials
2. Add `GOOGLE_REDIRECT_URI` to Authorized redirect URIs.
3. Fill `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` in `.env`.

## Auth Flow

```
desktop browser
  → GET /auth/google?device_id=...&callback=<loopback>
  → Google consent screen
  → GET /auth/callback?code=...&state=...
  → issues access + refresh tokens
  → loopback redirect to the desktop app
```

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/auth/google?device_id=...&callback=<loopback>` | Initiate OAuth flow |
| `GET` | `/auth/callback?code&state` | OAuth callback (Google redirects here) |
| `POST` | `/auth/refresh` | Refresh access token (form: `refresh_token`) |
| `POST` | `/auth/logout` | Revoke refresh token (form: `refresh_token`) |
| `GET` | `/auth/me` | Get current user info (Bearer token required) |
| `GET` | `/health` | Health check |
