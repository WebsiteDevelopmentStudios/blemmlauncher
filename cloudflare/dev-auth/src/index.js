/**
 * BlemmLauncher Developer Authentication Worker
 *
 * Credentials are stored in Cloudflare D1. Passwords are stored as PBKDF2
 * hashes with per-user salts, never as plaintext.
 *
 * Required bindings:
 *   DB -> D1 database named blemmlauncher-devs
 *
 * Required secret:
 *   DEV_AUTH_SECRET
 *
 * /login is used by the desktop launcher.
 * /admin is a small browser-only management page protected by the same secret.
 */

const encoder = new TextEncoder();
const PBKDF2_ITERATIONS = 100000;
const TOKEN_TTL_SECONDS = 3600;

function b64url(bytes) {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function fromB64url(value) {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - value.length % 4) % 4);
  const binary = atob(normalized);
  return Uint8Array.from(binary, c => c.charCodeAt(0));
}

function hex(bytes) {
  return Array.from(bytes, b => b.toString(16).padStart(2, "0")).join("");
}

function timingSafeEqual(a, b) {
  if (a.length !== b.length) return false;
  let result = 0;
  for (let i = 0; i < a.length; i++) result |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return result === 0;
}

async function derivePassword(password, saltBytes) {
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(password),
    "PBKDF2",
    false,
    ["deriveBits"]
  );
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", salt: saltBytes, iterations: PBKDF2_ITERATIONS, hash: "SHA-256" },
    key,
    256
  );
  return hex(new Uint8Array(bits));
}

async function hashPassword(password) {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const hash = await derivePassword(password, salt);
  return b64url(salt) + "$" + hash;
}

async function verifyPassword(password, stored) {
  const parts = String(stored || "").split("$");
  if (parts.length !== 2) return false;
  try {
    const salt = fromB64url(parts[0]);
    const actual = await derivePassword(password, salt);
    return timingSafeEqual(actual, parts[1]);
  } catch {
    return false;
  }
}

async function signToken(payload, secret) {
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  return b64url(new Uint8Array(
    await crypto.subtle.sign("HMAC", key, encoder.encode(payload))
  ));
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store"
    }
  });
}

function html(body, status = 200) {
  return new Response(body, {
    status,
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store"
    }
  });
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

async function parseJson(request) {
  try {
    return await request.json();
  } catch {
    return null;
  }
}

async function verifyToken(token, secret) {
  if (!token || !secret) return null;
  const parts = token.split(".");
  if (parts.length !== 2) return null;
  try {
    const expected = await signToken(parts[0], secret);
    if (!timingSafeEqual(expected, parts[1])) return null;
    const payload = JSON.parse(new TextDecoder().decode(fromB64url(parts[0])));
    if (!payload?.username || !payload?.exp || payload.exp < Math.floor(Date.now() / 1000)) return null;
    return payload;
  } catch { return null; }
}

async function requireOwner(request, env) {
  const supplied = request.headers.get("Authorization") || "";
  const token = supplied.startsWith("Bearer ") ? supplied.slice(7) : "";
  const identity = await verifyToken(token, env.DEV_AUTH_SECRET);
  return identity?.role === "owner" ? identity : null;
}

async function requireAdmin(request, env) {
  if (!env.DEV_AUTH_SECRET) return false;
  const supplied = request.headers.get("Authorization") || "";
  return supplied === "Bearer " + env.DEV_AUTH_SECRET;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/") {
      return html(`<!doctype html>
<html><head><meta charset="utf-8"><title>BlemmLauncher Dev Auth</title></head>
<body style="font-family:system-ui;background:#07110b;color:#9CFFBC;padding:40px">
<h1>BlemmLauncher Developer Authentication</h1>
<p>Developer authentication service is online.</p>
</body></html>`);
    }

    // Browser-only developer management page. The secret is entered into a
    // form and sent in an HTTPS Authorization header, never in the URL.
    if (request.method === "GET" && url.pathname === "/admin") {
      return html(`<!doctype html>
<html><head><meta charset="utf-8"><title>BlemmLauncher Developer Admin</title></head>
<body style="font-family:system-ui;background:#07110b;color:#d9ffe5;padding:32px;max-width:620px">
<h1>Developer Accounts</h1>
<p>Add or replace a developer account in the Cloudflare D1 database.</p>
<form id="f">
<label>Worker secret<br><input id="secret" type="password" required style="width:100%;padding:10px"></label><br><br>
<label>Username<br><input id="username" required maxlength="64" style="width:100%;padding:10px"></label><br><br>
<label>Password<br><input id="password" type="password" required minlength="8" style="width:100%;padding:10px"></label><br><br>
<button style="padding:10px 16px">Save developer</button>
</form>
<pre id="out"></pre>
<script>
f.addEventListener("submit", async e => {
  e.preventDefault();
  out.textContent = "Saving...";
  const r = await fetch("/admin/developer", {
    method: "POST",
    headers: {"content-type":"application/json","authorization":"Bearer " + secret.value},
    body: JSON.stringify({username: username.value, password: password.value})
  });
  out.textContent = await r.text();
});
</script>
</body></html>`);
    }

    if (request.method === "POST" && url.pathname === "/admin/developer") {
      if (!(await requireAdmin(request, env))) return json({ error: "Unauthorized." }, 401);
      if (!env.DB) return json({ error: "D1 binding DB is not configured." }, 500);

      const body = await parseJson(request);
      const username = typeof body?.username === "string" ? body.username.trim() : "";
      const password = typeof body?.password === "string" ? body.password : "";

      if (!/^[A-Za-z0-9_.-]{3,64}$/.test(username)) {
        return json({ error: "Username must be 3-64 characters: letters, numbers, _, ., or -." }, 400);
      }
      if (password.length < 8 || password.length > 256) {
        return json({ error: "Password must be 8-256 characters." }, 400);
      }

      const passwordHash = await hashPassword(password);
      await env.DB.prepare(
        "INSERT INTO developers (username, password_hash, role) VALUES (?, ?, 'developer') " +
        "ON CONFLICT(username) DO UPDATE SET password_hash = excluded.password_hash, role = CASE WHEN developers.role = 'owner' THEN developers.role ELSE 'developer' END"
      ).bind(username, passwordHash).run();

      return json({ saved: true, username });
    }

    if (request.method === "POST" && url.pathname === "/login") {
      await ensureOwner(env);
      if (!env.DB) return json({ error: "D1 binding DB is not configured." }, 500);

      const body = await parseJson(request);
      const username = typeof body?.username === "string" ? body.username.trim() : "";
      const password = typeof body?.password === "string" ? body.password : "";

      if (!username || !password) return json({ error: "Username and password are required." }, 400);

      const row = await env.DB.prepare(
        "SELECT username, password_hash, role FROM developers WHERE username = ? LIMIT 1"
      ).bind(username).first();

      if (!row || !(await verifyPassword(password, row.password_hash))) {
        return json({ error: "Invalid developer username or password." }, 401);
      }

      const now = Math.floor(Date.now() / 1000);
      const payload = b64url(encoder.encode(JSON.stringify({
        v: 1,
        username: row.username,
        role: row.role || "developer",
        iat: now,
        exp: now + TOKEN_TTL_SECONDS
      })));
      const signature = await signToken(payload, env.DEV_AUTH_SECRET);
      return json({
        authenticated: true,
        developer: true,
        username: row.username,
        role: row.role || "developer",
        token: payload + "." + signature,
        expires_at: now + TOKEN_TTL_SECONDS
      });
    }


    // Owner-only developer management API. Passwords are never returned.
    if (request.method === "GET" && url.pathname === "/developers") {
      if (!(await requireOwner(request, env))) return json({ error: "Owner authorization required." }, 403);
      const result = await env.DB.prepare(
        "SELECT username, role, created_at FROM developers ORDER BY username COLLATE NOCASE"
      ).all();
      return json({ developers: result.results || [] });
    }

    if (request.method === "POST" && url.pathname === "/developers") {
      if (!(await requireOwner(request, env))) return json({ error: "Owner authorization required." }, 403);
      const body = await parseJson(request);
      const username = typeof body?.username === "string" ? body.username.trim() : "";
      const password = typeof body?.password === "string" ? body.password : "";
      if (!/^[A-Za-z0-9_.-]{3,64}$/.test(username)) return json({ error: "Invalid username." }, 400);
      if (password.length < 8 || password.length > 256) return json({ error: "Password must be 8-256 characters." }, 400);
      if (username.toLowerCase() === "blemm") return json({ error: "The owner account cannot be created here." }, 400);
      const existing = await env.DB.prepare("SELECT username FROM developers WHERE username = ?").bind(username).first();
      if (existing) return json({ error: "That developer already exists." }, 409);
      await env.DB.prepare(
        "INSERT INTO developers (username, password_hash, role) VALUES (?, ?, 'developer')"
      ).bind(username, await hashPassword(password)).run();
      return json({ created: true, username, role: "developer" });
    }

    const resetMatch = url.pathname.match(/^\/developers\/([^/]+)\/reset$/);
    if (request.method === "POST" && resetMatch) {
      if (!(await requireOwner(request, env))) return json({ error: "Owner authorization required." }, 403);
      const username = decodeURIComponent(resetMatch[1]);
      if (username.toLowerCase() === "blemm") return json({ error: "The owner password cannot be reset here." }, 400);
      const body = await parseJson(request);
      const password = typeof body?.password === "string" ? body.password : "";
      if (password.length < 8 || password.length > 256) return json({ error: "Password must be 8-256 characters." }, 400);
      const result = await env.DB.prepare(
        "UPDATE developers SET password_hash = ? WHERE username = ? AND role = 'developer'"
      ).bind(await hashPassword(password), username).run();
      if (!result.meta?.changes) return json({ error: "Developer not found." }, 404);
      return json({ reset: true, username });
    }

    const deleteMatch = url.pathname.match(/^\/developers\/([^/]+)$/);
    if (request.method === "DELETE" && deleteMatch) {
      if (!(await requireOwner(request, env))) return json({ error: "Owner authorization required." }, 403);
      const username = decodeURIComponent(deleteMatch[1]);
      if (username.toLowerCase() === "blemm") return json({ error: "The owner account cannot be deleted." }, 400);
      const result = await env.DB.prepare(
        "DELETE FROM developers WHERE username = ? AND role = 'developer'"
      ).bind(username).run();
      if (!result.meta?.changes) return json({ error: "Developer not found." }, 404);
      return json({ deleted: true, username });
    }

    return json({ error: "Not found." }, 404);
  }
};
