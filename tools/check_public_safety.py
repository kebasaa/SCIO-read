#!/usr/bin/env python
"""Fail if files intended for commit contain credentials or user-home paths."""

from __future__ import annotations

import argparse
import os
import re
import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent   # tools/ -> repository root
PATTERNS = {
    "Windows user-home path": re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+", re.I),
    "WSL Windows user-home path": re.compile(r"/mnt/[a-z]/Users/", re.I),
    "Unix user-home path": re.compile(r"/(?:Users|home)/[^/\s]+/"),
    "credential in URL": re.compile(r"https?://[^/\s:@]+:[^/\s@]+@", re.I),
    "bearer token": re.compile(r"Authorization[^\r\n]{0,40}Bearer\s+[A-Za-z0-9._~-]{16,}", re.I),
    # Not anchored to a real line start: inside a .ipynb every source line is a
    # quoted, indented JSON string, so `^Token:` never matched and a real
    # (long-expired) token sat in a notebook undetected. Match after any
    # whitespace/quote run instead.
    "credential log field": re.compile(
        r"(?:^|[\s\"'\\])(?:Password|Token|Bearer):?\s*[A-Za-z0-9._~-]{20,}", re.I | re.M
    ),
    # `d['Token'] = '...'` / `token: "..."` - the assignment form the pattern
    # below misses because it only knows password/client_secret/access_token.
    "token assignment": re.compile(
        r"['\"]?\b(?:token|api_?key|auth)\b['\"]?\s*\]?\s*[=:]\s*['\"][A-Za-z0-9._~-]{20,}['\"]", re.I
    ),
    "token-bearing request id": re.compile(r"X-Request-ID:\s*\d+-[A-Za-z0-9._~-]{16,}", re.I),
    "literal secret assignment": re.compile(
        r"(?:password|client_secret|access_token)\s*[=:]\s*['\"][^'\"\r\n]{8,}['\"]", re.I
    ),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "AWS access-key id": re.compile(r"AKIA[0-9A-Z]{16}"),
    "GitHub token": re.compile(r"gh[opsu]_[A-Za-z0-9]{30,}"),
    "OpenAI key": re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
}


def candidate_names(staged_only: bool = False) -> list[str]:
    if staged_only:
        # Only what this commit actually introduces. The full scan walks ~1500
        # files including the 97 canonical scan records and takes ~40 s, which is
        # too slow for a pre-commit hook - and a slow hook is a bypassed hook.
        cmd = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM", "-z"]
    else:
        cmd = ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"]
    result = subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True)
    return [item.decode("utf-8", "surrogateescape")
            for item in result.stdout.split(b"\0") if item]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cached", action="store_true",
                        help="scan the exact staged snapshot instead of working files")
    parser.add_argument("--staged-only", action="store_true",
                        help="scan only files this commit adds or modifies (fast; for hooks)")
    args = parser.parse_args(argv)
    if args.staged_only:
        args.cached = True
    temp_index = None
    scan_root = ROOT
    if args.cached:
        temp_index = tempfile.TemporaryDirectory(prefix="scio-public-safety-")
        checkout = ["git", "checkout-index", f"--prefix={temp_index.name}{os.sep}"]
        names = candidate_names(args.staged_only)
        if args.staged_only:
            if not names:
                print("Public-safety check: nothing staged.")
                return 0
            checkout += ["--"] + names
        else:
            checkout.append("--all")
        subprocess.run(checkout, cwd=ROOT, check=True, capture_output=True)
        scan_root = Path(temp_index.name)
    findings = []
    for relative in candidate_names(args.staged_only):
        path = scan_root / relative
        if relative == Path(__file__).name or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        # Encoded sensor bytes can coincidentally contain key-like ASCII.  Scan
        # metadata, not the deliberately opaque base64/hex payload fields.
        if path.suffix.lower() == ".json":
            try:
                value = json.loads(text)
                if isinstance(value, dict):
                    for key in ("b64", "b64_data", "raw_hex", "raw_data"):
                        value.pop(key, None)
                    text = json.dumps(value)
            except json.JSONDecodeError:
                pass
        for name, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append((Path(relative).as_posix(), line, name))
    if findings:
        for path, line, name in findings:
            print(f"{path}:{line}: {name}")
        print(f"Public-safety check failed with {len(findings)} finding(s).")
        return 1
    target = "staged snapshot" if args.cached else "working tree"
    print(f"Public-safety check passed for {target}: no credentials or user-home paths detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
