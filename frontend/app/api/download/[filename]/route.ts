import { NextRequest, NextResponse } from 'next/server'

const BACKEND_URL =
  process.env.BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  'https://huggingface.co/spaces/Doaamostafa/bI-platform'

// Next.js 15: params is now a Promise — must be awaited
export async function GET(
  _req: NextRequest,
  context: { params: Promise<{ filename: string }> }
) {
  try {
    const { filename } = await context.params
    const safeFilename = filename.replace(/[^a-zA-Z0-9._-]/g, '')

    const backendResponse = await fetch(
      `${BACKEND_URL}/report/download/${safeFilename}`,
      { cache: 'no-store' }
    )

    if (!backendResponse.ok) {
      return NextResponse.json(
        { error: `File not found: ${backendResponse.status}` },
        { status: backendResponse.status }
      )
    }

    const buffer = await (await backendResponse.blob()).arrayBuffer()

    return new NextResponse(buffer, {
      headers: {
        'Content-Type': 'application/pdf',
        'Content-Disposition': `attachment; filename="${safeFilename}"`,
      },
    })
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json(
      { error: `Download failed: ${message}` },
      { status: 502 }
    )
  }
}