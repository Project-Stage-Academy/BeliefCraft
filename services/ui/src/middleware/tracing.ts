import { NextRequest, NextResponse } from 'next/server';
import { v4 as uuidv4 } from 'uuid';
import { logger } from '@/utils/logger';

export async function middleware(request: NextRequest) {
  const traceId = request.headers.get('x-request-id') || uuidv4();
  const startTime = Date.now();

  const childLogger = logger.child({ trace_id: traceId });

  childLogger.info({
    event: 'http_request_received',
    method: request.method,
    path: request.nextUrl.pathname,
  });

  const response = NextResponse.next();
  response.headers.set('x-request-id', traceId);

  const duration = Date.now() - startTime;

  childLogger.info({
    event: 'http_request_completed',
    method: request.method,
    path: request.nextUrl.pathname,
    duration_ms: duration,
  });

  return response;
}

export const config = {
  matcher: ['/api/:path*', '/'],
};
