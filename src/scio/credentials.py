"""Cached, encrypted SCiO account credentials + token retrieval.

The OAuth token the server issues is short-lived (seconds), so caching *it* is
useless. Instead we cache the account credentials, encrypted at rest, and log in
fresh each run. Behaviour:

* First use (or after a failed login): prompt for email + password, verify by
  logging in, and only on success save them to an encrypted, git-ignored file.
* Every later run: decrypt the file and log in automatically - no prompt.

Encryption: Fernet (AES-128-CBC + HMAC) with a key derived by PBKDF2 from a
*machine + user* secret, so the credential file only decrypts on this machine
for this user and is worthless if copied elsewhere or committed by accident.
This is encryption-at-rest against casual exposure, not protection from someone
who already has code execution as you on this machine. For stronger storage use
the OS keyring; see ``USE_KEYRING`` note below.
"""

from __future__ import annotations

import base64
import getpass
import json
import platform
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from . import cloud

from .paths import REPOSITORY_ROOT

CRED_FILE = REPOSITORY_ROOT / ".scio_credentials.enc"
_SALT = b"scio-read-credentials-v1"
_ITERATIONS = 200_000


def _fernet() -> Fernet:
    secret = f"{getpass.getuser()}|{platform.node()}|scio-read".encode("utf-8")
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=_SALT,
                     iterations=_ITERATIONS)
    return Fernet(base64.urlsafe_b64encode(kdf.derive(secret)))


def save_credentials(username: str, password: str, path: Path = CRED_FILE) -> Path:
    blob = _fernet().encrypt(json.dumps({"username": username, "password": password}).encode())
    path.write_bytes(blob)
    try:  # best-effort tighten perms (POSIX); harmless on Windows
        path.chmod(0o600)
    except OSError:
        pass
    return path


def load_credentials(path: Path = CRED_FILE):
    """Return (username, password) or None if missing/unreadable/undecryptable."""
    if not path.exists():
        return None
    try:
        data = json.loads(_fernet().decrypt(path.read_bytes()))
        return data["username"], data["password"]
    except (InvalidToken, ValueError, KeyError):
        return None


def clear_credentials(path: Path = CRED_FILE) -> bool:
    if path.exists():
        path.unlink()
        return True
    return False


def get_token(prompt_if_needed: bool = True, force_prompt: bool = False,
              path: Path = CRED_FILE, debug: bool = False) -> str:
    """Log in and return a bearer token, using cached credentials when possible.

    Prompts for credentials only if the encrypted file is missing/unreadable, if
    the cached login fails, or if ``force_prompt`` is set. On a successful
    interactive login the credentials are (re)saved.
    """
    if not force_prompt:
        creds = load_credentials(path)
        if creds:
            try:
                token = cloud.login(creds[0], creds[1], debug=debug)
                if debug:
                    print("Logged in with cached credentials.")
                return token
            except cloud.CloudError as e:
                print(f"Cached login failed ({e}); re-enter credentials.")
    if not prompt_if_needed:
        raise cloud.CloudError("no usable cached credentials and prompting disabled")

    username = input("SCiO account email: ").strip()
    password = getpass.getpass("Password (hidden): ")
    token = cloud.login(username, password, debug=debug)  # raises on failure
    save_credentials(username, password, path)
    print(f"Credentials verified and saved (encrypted) to {path.name}.")
    return token
