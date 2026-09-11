# Working on this repository

## Commit attribution

**Never add a Claude co-author trailer.** Do not append
`Co-Authored-By: Claude ...`, or any other Claude attribution, to a commit
message or a pull-request body. End the message on its last line of prose.

Commits are authored solely as **`kebasaa <muellerjonathan@gmx.net>`**. That
identity is pinned in this repository's local git config, so no `--author` flag is
needed.

This overrides the default Claude Code convention of adding a co-author trailer.
Commits made before 2026-09-11 still carry one; they are left as they are, and
this rule is not a reason to rewrite history.

## Before you commit

`tools/pre-commit` runs the credential and home-path scan on every commit.
Install it once per clone:

```bash
cp tools/pre-commit .git/hooks/pre-commit
```

## Two invariants worth knowing

- **`01_rawdata/` is append-only.** Nothing in it is modified or deleted;
  converters copy. The only exception is redacting a credential or personal data.
- **`src/` and `dev/` stay decoupled.** `pytest tests/` must pass with `dev/`
  deleted, and the root notebooks import only `scio`, never `scio_offline`.

Everything else — the device protocol, data formats, server API, and how to work
here — is in [`README.md`](README.md) and
[`documentation/HANDOFF.md`](documentation/HANDOFF.md).
