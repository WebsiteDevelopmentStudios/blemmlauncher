/**
 * BlemmLauncher Developer Authentication Worker
 *
 * Put this Worker behind Cloudflare Access. The /authorize endpoint is the
 * only endpoint that should be Access-protected. After Access authenticates
 * the developer, the Worker creates a short-lived signed login code and
 * redirects the desktop launcher to its localhost callback.
 *
 * Required Worker secret:
 *   DEV_AUTH_SECRET
 *
 * The secret is set with:
 *   wrangler secret put DEV_AUTH_SECRET
 */

const CODE_TTL_SECONDS = 120;
const encoder = new TextEncoder();

function b64url(bytes) {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function decodeB64url(value) {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - value.length % 4) % 4);
  const binary = atob(normalized);
  return Uint8Array.from(binary, c => c.charCodeAt(0));
}

async function sign(value, secret) {
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  return b64url(new Uint8Array(await crypto.subtle.sign("HMAC", key, encoder.encode(value))));
}

async function timingSafeEqual(a, b) {
  if (a.length !== b.length) return false;
  let result = 0;
  for (let i = 0; i < a.length; i++) result |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return result === 0;
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" }
  });
}

function html(body, status = 200) {
  return new Response(body, {
    status,
    headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" }
  });
}

function allowedRedirect(url) {
  try {
    const u = new URL(url);
    return (
      u.protocol === "http:" &&
      (u.hostname === "127.0.0.1" || u.hostname === "localhost") &&
      u.pathname === "/callback"
    );
  } catch {
    return false;
  }
}

function constantTimeCodePayload(payload, signature) {
  return payload + "." + signature;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/") {
      return html(`<!doctype html>
<html><head><meta charset="utf-8"><title>BlemmLauncher Dev Auth</title></head>
<body style="font-family:system-ui;background:#07110b;color:#9CFFBC;padding:40px">
<h1>BlemmLauncher Developer Authentication</h1>
<p>This endpoint is for the BlemmLauncher desktop developer login.</p>
</body></html>`);
    }

    if (request.method === "GET" && url.pathname === "/authorize") {
      if (!env.DEV_AUTH_SECRET) return json({ error: "Worker secret is not configured." }, 500);

      const redirect = url.searchParams.get("redirect");
      const state = url.searchParams.get("state");
      if (!redirect || !allowedRedirect(redirect) || !state || state.length > 128) {
        return json({ error: "Invalid login request." }, 400);
      }

      // Cloudflare Access adds the authenticated identity to this request.
      const email =
        request.headers.get("Cf-Access-Authenticated-User-Email") ||
        request.headers.get("cf-access-authenticated-user-email");

      if (!email) {
        return json({
          error: "Cloudflare Access did not provide an authenticated developer identity."
        }, 401);
      }

      const now = Math.floor(Date.now() / 1000);
      const payload = JSON.stringify({
        v: 1,
        iat: now,
        exp: now + CODE_TTL_SECONDS,
        email,
        state
      });
      const encodedPayload = b64url(encoder.encode(payload));
      const signature = await sign(encodedPayload, env.DEV_AUTH_SECRET);
      const code = constantTimeCodePayload(encodedPayload, signature);

      const callback = new URL(redirect);
      callback.searchParams.set("code", code);
      callback.searchParams.set("state", state);
      return Response.redirect(callback.toString(), 302);
    }

    if (request.method === "POST" && url.pathname === "/token") {
      if (!env.DEV_AUTH_SECRET) return json({ error: "Worker secret is not configured." }, 500);

      let body;
      try {
        body = await request.json();
      } catch {
        return json({ error: "Invalid JSON." }, 400);
      }

      const code = typeof body?.code === "string" ? body.code : "";
      if (!code || code.length > 10000) return json({ error: "Invalid code." }, 400);

      const dot = code.lastIndexOf(".");
      if (dot <= 0) return json({ error: "Invalid code." }, 401);

      const payload = code.slice(0, dot);
      const signature = code.slice(dot + 1);
      const expected = await sign(payload, env.DEV_AUTH_SECRET);
      if (!(await timingSafeEqual(signature, expected))) {
        return json({ error: "Invalid developer code." }, 401);
      }

      let claims;
      try {
        claims = JSON.parse(new TextDecoder().decode(decodeB64url(payload)));
      } catch {
        return json({ error: "Malformed developer code." }, 401);
      }

      const now = Math.floor(Date.now() / 1000);
      if (!claims || claims.v !== 1 || typeof claims.exp !== "number" || claims.exp < now) {
        return json({ error: "Developer code expired." }, 401);
      }

      return json({
        authenticated: true,
        developer: true,
        email: claims.email,
        expires_at: claims.exp
      });
    }

    return json({ error: "Not found." }, 404);
  }
};
