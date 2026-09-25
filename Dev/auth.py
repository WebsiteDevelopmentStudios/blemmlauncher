"""Basic local developer authentication for BlemmLauncher.

This is intentionally separate from the launcher GUI so it can later be
replaced/extended with Cloudflare Access authentication.

Passwords are never stored in plaintext. They are hashed with PBKDF2-HMAC-SHA256
and a random salt. The first-time setup asks for username, password, and password
confirmation.
"""

from __future__ import annotations

import getpass
import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path
from typing import Optional

DEV_DIR = Path(__file__).resolve().parent
USERS_FILE = DEV_DIR / "users.json"
ITERATIONS = 310_000


def _load_users() -> dict:
    if not USERS_FILE.exists():
        return {}
    try:
        data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _save_users(users: dict) -> None:
    DEV_DIR.mkdir(parents=True, exist_ok=True)
    tmp = USERS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(users, indent=2), encoding="utf-8")
    os.replace(tmp, USERS_FILE)


def _hash_password(password: str, salt: bytes) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        ITERATIONS,
    )
    return digest.hex()


def _make_password_record(password: str) -> dict:
    salt = secrets.token_bytes(32)
    return {
        "salt": salt.hex(),
        "hash": _hash_password(password, salt),
        "iterations": ITERATIONS,
    }


def create_user(username: str, password: str, confirmation: str) -> None:
    username = username.strip()
    if not username:
        raise ValueError("Username cannot be empty.")
    if len(username) > 64:
        raise ValueError("Username is too long.")
    if password != confirmation:
        raise ValueError("Passwords do not match.")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")

    users = _load_users()
    if username in users:
        raise ValueError("That developer username already exists.")

    users[username] = _make_password_record(password)
    _save_users(users)


def verify_user(username: str, password: str) -> bool:
    users = _load_users()
    record = users.get(username)
    if not isinstance(record, dict):
        return False

    try:
        salt = bytes.fromhex(str(record["salt"]))
        expected = str(record["hash"])
        iterations = int(record.get("iterations", ITERATIONS))
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
        ).hex()
        return hmac.compare_digest(actual, expected)
    except (KeyError, ValueError, TypeError):
        return False


def login() -> Optional[str]:
    print("\n=== BlemmLauncher Developer Login ===")
    username = input("Developer username: ").strip()
    password = getpass.getpass("Developer password: ")

    if verify_user(username, password):
        print("Login successful.")
        return username

    print("Invalid developer username or password.")
    return None


def setup() -> None:
    print("\n=== Create BlemmLauncher Developer Account ===")
    username = input("Developer username: ").strip()
    password = getpass.getpass("Developer password: ")
    confirmation = getpass.getpass("Confirm password: ")

    try:
        create_user(username, password, confirmation)
    except ValueError as exc:
        print("Setup failed:", exc)
        return

    print("Developer account created successfully.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="BlemmLauncher developer authentication")
    parser.add_argument("--setup", action="store_true", help="create the first developer account")
    args = parser.parse_args()

    if args.setup:
        setup()
    else:
        login()
