/**
 * Next.js API Route — /api/download/[filename]
 * Proxies PDF file downloads from the backend through Vercel.
 * Needed because direct cross-origin file downloads also trigger CORS.
 */

import { NextRequest, NextResponse } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL || 
                    process.env.NEXT_PUBLIC_API_URL || 
                    'https://huggingface.co/spaces/Doaamostafa/bI-platform'

export async function GET(
  _req: NextRequest,
  { params }: { params: { filename: string } }
) {
  try {
    const { filename } = params
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

    const blob = await backendResponse.blob()
    const buffer = await blob.arrayBuffer()

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
