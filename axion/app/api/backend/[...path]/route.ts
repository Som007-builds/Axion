// Server-side proxy for write/compute backend endpoints.
//
// The browser must never hold the backend API key: anything that spends LLM
// tokens or mutates the graph is proxied through this route handler, which
// injects `X-API-Key` from the server-only AXION_API_KEY environment variable.
//
// Read-only endpoints are still called directly from the browser (see
// lib/api-client.ts) — they require no credentials.

import { NextRequest, NextResponse } from 'next/server'

const API_BASE =
  process.env.AXION_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  'http://localhost:8000'

const API_KEY = process.env.AXION_API_KEY || ''

// Explicit allowlist: only these paths may be proxied. Everything else 404s,
// so this cannot be abused as an open proxy.
const ALLOWED: RegExp[] = [
  /^query$/,
  /^experiments\/[A-Za-z0-9_:-]+\/design$/,
  /^confidence\/recalculate$/,
  /^ingestion\/trigger$/,
  /^ingestion\/custom$/,
]

async function proxy(request: NextRequest, path: string[] | undefined) {
  const endpoint = (path ?? []).join('/')

  if (!ALLOWED.some((pattern) => pattern.test(endpoint))) {
    return NextResponse.json({ detail: 'Not found' }, { status: 404 })
  }

  if (!API_KEY) {
    return NextResponse.json(
      {
        detail:
          'Compute endpoints are disabled: AXION_API_KEY is not configured on the web server.',
      },
      { status: 503 }
    )
  }

  let body: string | undefined
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    const text = await request.text()
    body = text.length > 0 ? text : undefined
  }

  try {
    const upstream = await fetch(`${API_BASE}/api/${endpoint}${request.nextUrl.search}`, {
      method: request.method,
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': API_KEY,
      },
      body,
      cache: 'no-store',
    })

    const text = await upstream.text()
    return new NextResponse(text, {
      status: upstream.status,
      headers: {
        'Content-Type': upstream.headers.get('content-type') || 'application/json',
      },
    })
  } catch {
    return NextResponse.json({ detail: 'Backend unreachable' }, { status: 502 })
  }
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params
  return proxy(request, path)
}

export function GET() {
  return NextResponse.json({ detail: 'Method not allowed' }, { status: 405 })
}
