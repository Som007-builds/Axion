// Server-side proxy for credentialled backend endpoints.
//
// The browser must never hold the backend API key: anything that spends LLM
// tokens, mutates the graph, or returns the result of queued work is proxied
// through this route handler, which injects `X-API-Key` from the server-only
// AXION_API_KEY environment variable.
//
// Public read-only endpoints are still called directly from the browser (see
// lib/api-client.ts) — they require no credentials.

import { NextRequest, NextResponse } from 'next/server'

const API_BASE =
  process.env.AXION_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  'http://localhost:8000'

const API_KEY = process.env.AXION_API_KEY || ''

type Rule = { method: 'GET' | 'POST'; pattern: RegExp }

// Explicit allowlist: only these method+path pairs may be proxied. Everything
// else 404s, so this cannot be abused as an open proxy.
const ALLOWED: Rule[] = [
  { method: 'POST', pattern: /^query$/ },
  { method: 'POST', pattern: /^experiments\/[A-Za-z0-9_:-]+\/design$/ },
  { method: 'POST', pattern: /^confidence\/recalculate$/ },
  { method: 'POST', pattern: /^ingestion\/trigger$/ },
  { method: 'POST', pattern: /^ingestion\/custom$/ },
  // Job results carry the research report, so they are key-guarded too.
  { method: 'GET', pattern: /^jobs\/[A-Za-z0-9_-]{1,64}$/ },
]

let warnedMissingKey = false

async function proxy(request: NextRequest, path: string[] | undefined) {
  const endpoint = (path ?? []).join('/')
  const method = request.method === 'HEAD' ? 'GET' : request.method

  if (!ALLOWED.some((rule) => rule.method === method && rule.pattern.test(endpoint))) {
    return NextResponse.json({ detail: 'Not found' }, { status: 404 })
  }

  if (!API_KEY) {
    // Log once per process so an operator can see why the UI is failing
    // without the message being repeated on every request.
    if (!warnedMissingKey) {
      console.warn(
        '[axion] AXION_API_KEY is not set on the web server: credentialled endpoints are disabled.'
      )
      warnedMissingKey = true
    }
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

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params
  return proxy(request, path)
}
