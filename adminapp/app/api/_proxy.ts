import { NextRequest, NextResponse } from "next/server";

const backendBase = process.env.INKSIGHT_BACKEND_API_BASE?.replace(/\/$/, "") || "http://127.0.0.1:8080";

function passthroughHeaders(req: NextRequest, extra?: Record<string, string>): Headers {
  const headers = new Headers(extra || {});
  const cookie = req.headers.get("cookie");
  const authorization = req.headers.get("authorization");
  if (cookie) headers.set("cookie", cookie);
  if (authorization) headers.set("authorization", authorization);
  return headers;
}

export async function proxyAdmin(req: NextRequest, path: string[]) {
  const search = req.nextUrl.search || "";
  const target = `${backendBase}/api/admin/${path.join("/")}${search}`;
  const body = req.method === "GET" || req.method === "HEAD" ? undefined : await req.arrayBuffer();

  const upstream = await fetch(target, {
    method: req.method,
    headers: passthroughHeaders(req, body ? { "content-type": req.headers.get("content-type") || "application/json" } : undefined),
    body,
    cache: "no-store",
  });

  const response = new NextResponse(await upstream.arrayBuffer(), {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") || "application/json",
    },
  });

  const setCookie = upstream.headers.get("set-cookie");
  if (setCookie) response.headers.set("set-cookie", setCookie);
  return response;
}
