import { describe, expect, it } from "vitest";
import { NextRequest } from "next/server";
import { middleware } from "../../middleware";

describe("middleware auth redirection", () => {
  it("redirects logged-in visitor on landing page to dashboard", () => {
    const req = new NextRequest("http://localhost:3000/", {
      headers: {
        cookie: "era_session=valid-session-jwt-token",
      },
    });

    const res = middleware(req);
    expect(res?.status).toBe(307);
    expect(res?.headers.get("location")).toBe("http://localhost:3000/dashboard");
  });

  it("redirects logged-in visitor on login page to dashboard", () => {
    const req = new NextRequest("http://localhost:3000/login", {
      headers: {
        cookie: "era_session=valid-session-jwt-token",
      },
    });

    const res = middleware(req);
    expect(res?.status).toBe(307);
    expect(res?.headers.get("location")).toBe("http://localhost:3000/dashboard");
  });

  it("redirects logged-in visitor on signup page to dashboard", () => {
    const req = new NextRequest("http://localhost:3000/signup", {
      headers: {
        cookie: "era_session=valid-session-jwt-token",
      },
    });

    const res = middleware(req);
    expect(res?.status).toBe(307);
    expect(res?.headers.get("location")).toBe("http://localhost:3000/dashboard");
  });

  it("allows anonymous visitor to view landing page without redirect", () => {
    const req = new NextRequest("http://localhost:3000/", {
      headers: {
        cookie: "anon_id=anonymous-visitor-id",
      },
    });

    const res = middleware(req);
    // NextResponse.next() returns response with x-middleware-next header and no redirect location
    expect(res?.headers.get("location")).toBeNull();
  });

  it("allows unauthenticated visitor without any cookies to view landing page", () => {
    const req = new NextRequest("http://localhost:3000/");

    const res = middleware(req);
    expect(res?.headers.get("location")).toBeNull();
  });

  it("allows visitor with empty session cookie to view landing page", () => {
    const req = new NextRequest("http://localhost:3000/", {
      headers: {
        cookie: "era_session=",
      },
    });

    const res = middleware(req);
    expect(res?.headers.get("location")).toBeNull();
  });

  it("allows visitor with 'deleted' session cookie to view landing page", () => {
    const req = new NextRequest("http://localhost:3000/", {
      headers: {
        cookie: "era_session=deleted",
      },
    });

    const res = middleware(req);
    expect(res?.headers.get("location")).toBeNull();
  });

  it("redirects logged-in visitor on landing page with query params", () => {
    const req = new NextRequest("http://localhost:3000/?utm_source=twitter", {
      headers: {
        cookie: "era_session=valid-session-jwt-token",
      },
    });

    const res = middleware(req);
    expect(res?.status).toBe(307);
    expect(res?.headers.get("location")).toBe("http://localhost:3000/dashboard");
  });
});
