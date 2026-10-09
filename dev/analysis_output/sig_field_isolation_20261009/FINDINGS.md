# Which field binds a blob — single-variable isolation (2026-10-09)

Goal: find the request field the server uses to accept/reject each side of a scan — the most
likely input to the per-device key. Method: start from the owner's fully valid scan (decodes 200)
and change **one request identity field at a time**, keeping all owner blobs; plus two
mixed-identity cross-checks. Live, 8 requests, 20 s apart, clean run (no halt).
Script: `dev/scripts/probe_signature_field_isolation.py`.

| job | request id / tag | blobs | status | flagged side |
|---|---|---|---|---|
| control_initial / control_mid / control_final | owner / owner | all owner | **200**, valid 331-band | — |
| owner_blobs__id_fw138 | **fw-138** / owner | all owner | **400 `Bad_sample_signature`** | `sample` |
| owner_blobs__tag_fw138 | owner / **fw-138** | all owner | **500 Server error** | — |
| owner_blobs__id_tag_fw138 | **fw-138 / fw-138** | all owner | **400 `Bad_sample_signature`** | `sample` |
| fw138white__id_fw138_tag_owner | **fw-138** / owner | owner sample + fw-138 white | **400** | `sample` |
| fw138white__id_owner_tag_fw138 | owner / **fw-138** | owner sample + fw-138 white | **400** | `white` |

## Result: the binding field is `device_id`

The decisive row is `owner_blobs__id_fw138`: with **100% owner blobs**, changing **only** the request
`device_id` turns a valid 200 into `400 Bad_sample_signature`. So the server does not merely read an
id embedded in the blob — it validates each blob against the **request `device_id`** and rejects the
side whose true origin device ≠ that id. The flagged side tracks `device_id` across every row:

- id = fw-138 → the owner sample is the mismatch → flags `sample` (checked before white).
- id = owner, fw-138 white → the fw-138 white is the mismatch → flags `white`.

This is the behavior of a per-blob integrity/signature **keyed by `device_id`** (equivalently,
a decrypt-then-verify whose key is selected by `device_id`).

`i2s_tag_config` is also used, but differently: changing **only** the tag (owner `20150812-e:PRODUCTION`
→ fw-138 bare `20150812:PRODUCTION`) returned **500 Server error**, not a clean signature rejection.
So the tag is parsed and acted on (not ignored) — the `-e` "edition" suffix matters — but it behaves
like a config/edition selector rather than the signature key. When `device_id` is foreign too
(`owner_blobs__id_tag_fw138`), the signature check fails first and the clean 400 returns.

## Implication for decode

Localizes the key input: the per-blob keystream/signature is a function of `device_id`. And
`device_id` is itself derived from the sensor aptina id (fw-138 `device_id E02E60F46B7CD55F` =
aptina `2ee0f4607c6b5fd5` with byte-pairs reversed). The firmware target therefore narrows to the
KDF mapping `device_id`/aptina → the per-blob key.

## Limits

This identifies the field the server uses to validate each blob; it does **not** reveal the signature
/ KDF algorithm, prove `device_id` is the entire key (vs a tweak/salt with additional per-blob
material), or yield the key itself. No offline decode results. The sample side is checked before the
white side (first failure reported). The tag-only `500` is a server-side exception; do not
over-interpret it beyond "the tag is used and its edition format matters". Live requests used the
owner's own token and scan plus the project's contributed fw-138 white; no device operation.
