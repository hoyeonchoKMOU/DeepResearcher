import { NextRequest } from 'next/server';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ id: string }> }
) {
  console.log('[Next.js SSE] Route handler called');

  const { id: projectId } = await context.params;
  console.log('[Next.js SSE] Project ID:', projectId);

  // Create a connection to the backend SSE
  const backendUrl = `http://localhost:8000/api/research/${projectId}/stream`;
  console.log('[Next.js SSE] Connecting to backend:', backendUrl);

  try {
    const response = await fetch(backendUrl, {
      headers: {
        'Accept': 'text/event-stream',
        'Cache-Control': 'no-cache',
      },
    });

    console.log('[Next.js SSE] Backend response status:', response.status);

    if (!response.ok) {
      console.error('[Next.js SSE] Backend error:', response.status);
      return new Response(JSON.stringify({ error: 'Backend error' }), {
        status: response.status,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    if (!response.body) {
      console.error('[Next.js SSE] No response body');
      return new Response(JSON.stringify({ error: 'No response body' }), {
        status: 500,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // Create a ReadableStream that manually reads from the backend
    const encoder = new TextEncoder();
    const decoder = new TextDecoder();

    const stream = new ReadableStream({
      async start(controller) {
        console.log('[Next.js SSE] Starting stream read');
        const reader = response.body!.getReader();

        try {
          while (true) {
            const { done, value } = await reader.read();

            if (done) {
              console.log('[Next.js SSE] Backend stream ended');
              controller.close();
              break;
            }

            // Pass through the data
            const text = decoder.decode(value, { stream: true });
            console.log('[Next.js SSE] Forwarding chunk:', text.substring(0, 50));
            controller.enqueue(value);
          }
        } catch (error) {
          console.error('[Next.js SSE] Stream read error:', error);
          controller.error(error);
        }
      },
      cancel() {
        console.log('[Next.js SSE] Stream cancelled by client');
      }
    });

    console.log('[Next.js SSE] Returning streaming response');

    return new Response(stream, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache, no-transform',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no',
      },
    });
  } catch (error) {
    console.error('[Next.js SSE] Connection error:', error);
    return new Response(JSON.stringify({ error: 'Connection failed' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
