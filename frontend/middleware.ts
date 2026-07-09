import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

/**
 * Next.js Edge Middleware managing session authentication redirects.
 * Validates presence of the `aura_token` cookie for private routes, redirecting
 * unauthenticated requests back to `/login`.
 *
 * @param request - Next.js incoming HTTP request object.
 * @returns NextResponse configuration (redirect or continuation).
 */
export function middleware(request: NextRequest): NextResponse {
  const token = request.cookies.get('aura_token')?.value;
  const { pathname } = request.nextUrl;

  // Define public files/assets/paths that should never be protected or redirected
  if (
    pathname.startsWith('/api') ||
    pathname.startsWith('/_next') ||
    pathname.includes('.') ||
    pathname === '/login'
  ) {
    // If logged in and trying to access /login, redirect to /dashboard
    if (token && pathname === '/login') {
      return NextResponse.redirect(new URL('/dashboard', request.url));
    }
    return NextResponse.next();
  }

  // For any other route (which includes /, /dashboard, /devices, /models, /scripts, /deployments, /monitoring)
  if (!token) {
    return NextResponse.redirect(new URL('/login', request.url));
  }

  return NextResponse.next();
}
