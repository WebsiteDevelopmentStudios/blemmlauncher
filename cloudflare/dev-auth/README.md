# BlemmLauncher Cloudflare Developer Authentication

This Worker provides BlemmLauncher's developer username/password login.

## Cloudflare setup

Create a D1 database named:

```
blemmlauncher-devs
```

Create the table:

```sql
CREATE TABLE developers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Bind that D1 database to the Worker as:

```
DB
```

Also create the Worker secret:

```
DEV_AUTH_SECRET
```

The secret must be long and random. Do not put it in GitHub.

## Add a developer account

After deploying the Worker, open:

```
https://blemmlauncher-dev-auth.wowgrayhaha.workers.dev/admin
```

Enter the Worker secret, a developer username, and a password of at least 8 characters.

The Worker hashes the password with PBKDF2 + a unique salt before saving it to D1. The plaintext password is never stored.

## Launcher setup

Set:

```
BLEMM_DEV_AUTH_URL=https://blemmlauncher-dev-auth.wowgrayhaha.workers.dev
```

The developer login appears only under:

**BlemmLauncher → Profile → Developer Access**

The launcher sends the credentials to `/login` over HTTPS. It does not save the developer password locally.

The Worker returns a short-lived signed authentication token after successful login.
