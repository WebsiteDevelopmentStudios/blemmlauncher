# BlemmLauncher Dev Authentication

This folder contains the developer-only authentication layer.

## First setup

From the repository root:

```bash
python -m Dev.auth --setup
```

It asks for:

1. Developer username
2. Password
3. Password confirmation

Passwords are stored as salted PBKDF2-HMAC-SHA256 hashes, not plaintext.

## Login

```bash
python -m Dev.auth
```

## Cloudflare

This local login is deliberately kept separate from Cloudflare. If you use
Cloudflare Access later, the Access identity can become the authentication
source instead of storing developer credentials locally. Do not put a
Cloudflare API token or password directly into this repository.
