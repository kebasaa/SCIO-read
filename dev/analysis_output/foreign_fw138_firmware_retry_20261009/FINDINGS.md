# Firmware-upgrade retry for the fw-138 unit (2026-10-09)

Re-ran the firmware-upgrade request against the contributor's fw-138 unit at Vitaly's request
(`probe_foreign_firmware.py`, 4 live GETs 20 s apart). This is a faithful repeat of the
2026-10-08 campaigns (`foreign_fw138_20261008/`, `contributor_fw138_exact4_20261008_network/`).

Endpoint: `GET https://api.consumerphysics.com/v1/device/{ble_id}/firmware-upgrade`, ble_id
`EBA03B00004C99B4`, tag `20150812:PRODUCTION`.

| job | versions reported | result |
|---|---|---|
| foreign_all_zero | all `0x00` | 200, `{"new_version":null}` |
| foreign_real_fw138 | `7C/11/0C/8A`, tables `0x01` | 200, `{"new_version":null}` |
| foreign_tables_outdated | `7C/11/0C/8A`, tables `0x00` | 200, `{"new_version":null}` |
| own_device_control | owner fw-147 | 200, `{"new_version":null}` |

All four responses are byte-identical, 51 bytes, SHA-256
`f7bb8314e735cf6b05f60993ae05cd2e6150ea12f65c0e6d9d0cdd3209a08a0d` — the same empty "no update"
body the owner's own up-to-date device receives. **No firmware files offered; nothing recovered.**

Verdict: the firmware-upgrade route returns nothing for the fw-138 ble_id, identical to prior runs.
Bounded negative — null for these parameters on this account; not proof the images are unavailable
to every authorized client.
