import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/** Redirect authenticated visitors directly to the dashboard when they open the
 *  landing page or auth pages.
 */
export function middleware(request: NextRequest) {
  const session = request.cookies.get("era_session");
  const { pathname } = request.nextUrl;

  const sessionToken = session?.value?.trim();
  if (sessionToken && sessionToken.length > 0 && sessionToken !== "deleted") {
    if (pathname === "/" || pathname === "/login" || pathname === "/signup") {
      const url = request.nextUrl.clone();
      url.pathname = "/dashboard";
      url.search = "";
      return NextResponse.redirect(url);
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/", "/login", "/signup"],
};
