import { NextRequest, NextResponse } from 'next/server'

const BACKEND_URL =
  process.env.BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  'https://huggingface.co/spaces/Doaamostafa/bI-platform'

// Next.js 15: params is now a Promise — must be awaited
export async function GET(
  _req: NextRequest,
  context: { params: Promise<{ sessionId: string }> }
) {
  try {
    const { sessionId } = await context.params

    const backendResponse = await fetch(`${BACKEND_URL}/history/${sessionId}`, {
      headers: { 'Content-Type': 'application/json' },
      cache: 'no-store',
    })

    if (!backendResponse.ok) {
      return NextResponse.json(
        { error: `Backend error: ${backendResponse.status}` },
        { status: backendResponse.status }
      )
    }

    return NextResponse.json(await backendResponse.json())
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json(
      { error: `Failed to reach backend: ${message}` },
      { status: 502 }
    )
  }
}