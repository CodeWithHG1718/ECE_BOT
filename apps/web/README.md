# Signal web

The Signal 2.0 frontend is a Next.js App Router app built with TypeScript and Tailwind CSS. It consumes the existing FastAPI `/api/v1` contract and does not include academic fixtures.

Use Node.js 20.9 or newer.

## Run locally

In PowerShell, from `apps/web/`:

```powershell
npm install
Copy-Item .env.example .env.local
npm run dev
```

Run the API in a second terminal from the repository root:

```powershell
uvicorn backend.app.main:app --reload
```

Open `http://localhost:3000`. Set `NEXT_PUBLIC_SIGNAL_API_BASE_URL` in `.env.local` only when the API uses a different service URL. It is a browser-visible URL and must not contain credentials. The API CORS allowlist must include the frontend origin.

Anonymous session credentials stay in `sessionStorage` and are sent only in `X-Session-Token` headers. They are not written to URLs or application logs.
