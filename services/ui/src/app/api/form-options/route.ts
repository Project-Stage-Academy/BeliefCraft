import { NextResponse } from 'next/server';

const ENV_API_URL = process.env.VITE_ENV_API_URL ?? 'http://localhost:8000';

export async function GET() {
  const resp = await fetch(`${ENV_API_URL}/api/v1/form-options`, {
    cache: 'no-store',
  });

  if (!resp.ok) {
    const detail = await resp.text();
    return NextResponse.json({ detail }, { status: resp.status });
  }

  const data = await resp.json();
  return NextResponse.json(data);
}
