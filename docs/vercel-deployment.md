# Vercel deployment

Run Vercel CLI from the repository root, with Root Directory left at the repository root in project settings.

## Confirmed services and routes

- `web` (`apps/web`, Next.js): public at `/`, including browser `/api/v1/*` requests handled by a Next.js runtime proxy.
- `backend` (`backend`, FastAPI, `app.main:app`): internal only. Its existing `/api/v1/*` paths are preserved by the proxy.
- `web` declares the `backend` binding as `BACKEND_URL`. Vercel injects it into runtime functions; never configure this variable manually or read it during a build.
- `bot` is Telegram long polling and `ingestion` is an offline pipeline. Neither is an HTTP service. They are excluded from this deployment, rather than creating nonfunctional service entries. Hosting the bot as a daemon or converting it to a webhook is a separate decision.

## Required setup

1. Sign in with `npx vercel login` and select the intended Vercel account/team/project.
2. Provision a persistent PostgreSQL database. Configure a separate `DATABASE_URL` for each Vercel environment (Development, Preview, Production). Local SQLite cannot persist deployed profiles/conversations.
3. Configure the backend model environment variables in Vercel: `OPENAI_CHAT_API_KEY`, `OPENAI_CHAT_MODEL`, and the Azure-compatible `OPENAI_CHAT_BASE_URL` when used. For dense retrieval also configure `EMBEDDING_PROVIDER`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`, and `AZURE_OPENAI_API_VERSION` as appropriate. Do not copy Telegram credentials or unrelated local secrets. Do not set `BACKEND_URL`.
4. Clear any old `NEXT_PUBLIC_SIGNAL_API_BASE_URL` value in Vercel. Browser requests now default to same-origin `/api/v1`.
5. From the repository root, run `npx vercel dev` to exercise both services and their injected binding. Standalone `npm run dev` still supports a local Python backend through `SIGNAL_BACKEND_URL`, defaulting to `http://127.0.0.1:8000` on the server only.
6. After confirming the service names, public routing and binding, deploy a Preview using `npx vercel`. Verify profile persistence, timetable and chat; promote/deploy Production with `npx vercel --prod` when ready.

## Build and database behavior

The backend build copies the required existing academic JSON/JSONL into its function bundle. It never runs ingestion or embeddings, and does not include the raw timetable PDF/student rosters, local database, local vector stores, or `.env` credentials.

`backend/build_vercel.py` runs the existing additive schema compatibility changes and academic seed loader against the configured PostgreSQL database, protected by a PostgreSQL advisory lock for concurrent builds. Production function cold starts do not reseed the database. Existing deployments may share their environment's database; keep Preview and Production separate. The build stops if the database or academic inputs are missing.

The runtime rejects missing/PostgreSQL-incompatible `DATABASE_URL` on Vercel instead of silently losing session data in ephemeral SQLite. The packaged records remain the same authoritative sources used locally. Existing external embedding indexes are not automatically uploaded into a fresh hosted database; structured academic lookups and keyword fallback remain available.

The Next.js proxy forwards GET/POST/PUT, query strings, JSON content type and `X-Session-Token` to the bound service. Responses are not cached. Authentication remains enforced by FastAPI. The internal binding URL and backend credentials never enter the browser bundle.

## Reference

- https://vercel.com/docs/services
- https://vercel.com/docs/services/bindings
- https://vercel.com/kb/guide/python-backend-on-vercel
