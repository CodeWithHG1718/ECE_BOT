import type { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  // Bindings exist only inside runtime functions; never resolve this during builds.
  const base = process.env.BACKEND_URL || process.env.SIGNAL_BACKEND_URL ||
    (process.env.VERCEL ? undefined : "http://127.0.0.1:8000");
  if (!base) return Response.json({ error: { code: "unavailable", message: "Backend binding is not configured." } }, { status: 503 });
  const { path } = await context.params;
  const target = new URL(`api/v1/${path.map(encodeURIComponent).join("/")}`, base.endsWith("/") ? base : `${base}/`);
  target.search = request.nextUrl.search;
  const headers = new Headers({ Accept: "application/json" });
  for (const name of ["content-type", "x-session-token"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  try {
    const body = request.method === "GET" ? undefined : await request.arrayBuffer();
    if (body && body.byteLength > 32768) return Response.json({ error: { code: "request_too_large", message: "Request body exceeds the configured limit." } }, { status: 413 });
    const upstream = await fetch(target, { method: request.method, headers, body, cache: "no-store", redirect: "manual", signal: AbortSignal.timeout(55_000) });
    return new Response(upstream.body, { status: upstream.status, headers: {
      "Content-Type": upstream.headers.get("content-type") || "application/json",
      "Cache-Control": "no-store",
    } });
  } catch {
    return Response.json({ error: { code: "unavailable", message: "The academic service is temporarily unavailable." } }, { status: 502 });
  }
}

export { proxy as GET, proxy as POST, proxy as PUT };
