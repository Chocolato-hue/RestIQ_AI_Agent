import { NextRequest } from 'next/server';

const AGENT_URL = process.env.AGENT_SERVER_URL || 'http://localhost:8000';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    
    const response = await fetch(`${AGENT_URL}/api/copilotkit`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error(`Backend CopilotKit returned error: ${response.status} - ${errorText}`);
      return new Response(errorText, { status: response.status });
    }

    // Since ag-ui-adk streams back the response events, we want to forward the stream headers and body directly
    const contentType = response.headers.get('Content-Type') || 'application/json';

    return new Response(response.body, {
      status: response.status,
      headers: {
        'Content-Type': contentType,
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
      },
    });
  } catch (error: any) {
    console.error('Error in CopilotKit API Route:', error);
    return new Response(JSON.stringify({ error: error.message || 'Internal Server Error' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
