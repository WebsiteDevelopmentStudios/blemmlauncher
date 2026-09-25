# BlemmLauncher Developer Authentication

BlemmLauncher uses **Cloudflare Access + a Cloudflare Worker** for developer authentication.

## Configure the launcher

Set:

```text
BLEMM_DEV_AUTH_URL=https://blemmlauncher-dev-auth.<your-account>.workers.dev
```

Do not put a Cloudflare API token, Access secret, or Worker secret in the GitHub repository.

## Run the launcher

Open BlemmLauncher and go to:

```text
Profile → Developer Access → Developer Login
```

A browser opens for Cloudflare Access. After authentication, the browser returns to the running launcher through a temporary localhost callback.

## Cloudflare Worker

The Worker source is in:

```text
cloudflare/dev-auth/
```

Deploy it with Wrangler and set the Worker secret:

```bash
wrangler login
wrangler secret put DEV_AUTH_SECRET
wrangler deploy
```

Then protect the Worker `/authorize` endpoint with a Cloudflare Access application and allow only the developer identity/identities you want to authorize.

The launcher never receives or stores the Cloudflare password. The Worker issues a short-lived signed developer code after Access authentication.

## Important

The `blemm.devs.surf` hostname is a subdomain of `devs.surf`. It does not give the launcher control over the parent `devs.surf` zone. If Cloudflare requires a zone that you control for a custom hostname, use a domain/zone you actually control or use the Worker hostname while setting up the system.
