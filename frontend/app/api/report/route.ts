/**
 * Next.js API Route — /api/report
 * Proxies POST /report to the backend (same CORS fix as /api/chat).
 */

import { NextRequest, NextResponse } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL || 
                    process.env.NEXT_PUBLIC_API_URL || 
                    'https://huggingface.co/spaces/Doaamostafa/bI-platform'

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()

    const backendResponse = await fetch(`${BACKEND_URL}/report`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(process.env.BACKEND_API_KEY && {
          'Authorization': `Bearer ${process.env.BACKEND_API_KEY}`
        }),
      },
      body: JSON.stringify(body),
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
    console.error('[/api/report] Proxy error:', message)
    return NextResponse.json(
      { error: `Failed to reach backend: ${message}` },
      { status: 502 }
    )
  }
}
