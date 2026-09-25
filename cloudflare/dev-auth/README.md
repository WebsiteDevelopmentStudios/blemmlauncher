# BlemmLauncher Cloudflare Worker

This Worker provides the web side of BlemmLauncher's developer login.

## 1. Deploy

Install Wrangler and log in:

```bash
npm install -g wrangler
wrangler login
```

From this directory:

```bash
wrangler secret put DEV_AUTH_SECRET
wrangler deploy
```

When prompted for the secret, generate a long random value. **Never commit it.**

The Worker will receive a `workers.dev` URL such as:

```
https://blemmlauncher-dev-auth.<your-account>.workers.dev
```

## 2. Cloudflare Access

Create a Cloudflare Access application for the Worker hostname.

Protect:

```
/authorize
```

Allow only the developer identity/email(s) that should have access.

The Access policy must authenticate the user before the request reaches the Worker. The Worker reads the authenticated email from the Cloudflare Access identity header.

If your Cloudflare dashboard requires the hostname to be attached to a zone you control, use a custom hostname under a domain you control instead of trying to add `devs.surf`. Owning only `blemm.devs.surf` does not grant control of the `devs.surf` zone.

## 3. Launcher configuration

Set the desktop launcher environment variable:

```text
BLEMM_DEV_AUTH_URL=https://blemmlauncher-dev-auth.<your-account>.workers.dev
```

The launcher opens:

```/authorize?redirect=http://127.0.0.1:<random-port>/callback&state=<random-state>
```

After Cloudflare Access authenticates the developer, the Worker redirects back to the local launcher. The launcher exchanges the short-lived code at `/token`.

The code is signed and expires quickly. No Cloudflare API token, password, or secret is stored in the launcher.
