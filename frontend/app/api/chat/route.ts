/**
 * Next.js API Route — /api/chat
 *
 * WHY THIS EXISTS:
 * The backend runs on HuggingFace Spaces (or Railway/any external server).
 * Direct browser → backend calls are blocked by CORS because HuggingFace
 * does not send Access-Control-Allow-Origin headers for arbitrary origins.
 *
 * The fix: the browser calls THIS Next.js route (same origin = no CORS),
 * and THIS route calls the backend server-side (server → server = no CORS).
 *
 * Browser → Vercel (same origin, no CORS) → HuggingFace/Railway (server-side, no CORS)
 */

import { NextRequest, NextResponse } from 'next/server'

// Your backend URL — set this in Vercel environment variables
const BACKEND_URL = process.env.BACKEND_URL || 
                    process.env.NEXT_PUBLIC_API_URL || 
                    'https://huggingface.co/spaces/Doaamostafa/bI-platform'

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()

    const backendResponse = await fetch(`${BACKEND_URL}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        // Forward auth header if your backend requires it
        ...(process.env.BACKEND_API_KEY && {
          'Authorization': `Bearer ${process.env.BACKEND_API_KEY}`
        }),
      },
      body: JSON.stringify(body),
      // Important: don't cache chat responses
      cache: 'no-store',
    })

    if (!backendResponse.ok) {
      const errorText = await backendResponse.text()
      return NextResponse.json(
        { error: `Backend error: ${backendResponse.status} — ${errorText}` },
        { status: backendResponse.status }
      )
    }

    const data = await backendResponse.json()
    return NextResponse.json(data)

  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    console.error('[/api/chat] Proxy error:', message)
    return NextResponse.json(
      { error: `Failed to reach backend: ${message}` },
      { status: 502 }
    )
  }
}
