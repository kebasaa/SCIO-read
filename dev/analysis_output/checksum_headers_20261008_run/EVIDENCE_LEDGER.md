# Checksum campaign evidence ledger

## Initial and static findings

- Supported: candidate enumeration is 2,342 unique hypothesis keys, below the
  4,096 cap. Each profile has 1,156 generated keys; deltas add 30. Device sets
  remain separate. The owner DSP/Aptina fields are read from a hashed owner
  capture, not guessed or copied from another device.
- Supported: 180,266 enumerated jobs; no exact owner AES key/configuration
  duplicate in the prior bounded manifest. This does not establish complete
  coverage of earlier incompletely recorded searches.
- Association limit: current owner headers applied to historical captures are
  exploratory. Missing historical checksum truth weakens negative conclusions.
- Supported static observation: Lab `FirmwareUpgradeActivity` lines 199–205
  separates body/prefix and records the supplied prefix; line 326 passes outgoing
  firmware bytes to `performFileDownload`. No byte-sum computation is established.
- Supported static observation: Lab `SCiOBLeService` lines 869–875 expose list and
  header reads; lines 928–933 send supplied file bytes with write type. Its SDK
  wrapper `ScioInternalDevice` lines 1662–1664 misleadingly logs a read-list name.
  That log does not make the command a body read.
- Supported static observation: `ScioInternalDevice` lines 1104–1109 serializes
  returned readings via Base64. `getImage2SpecTag` is metadata, not a demonstrated
  KDF or codec implementation. The audit manifest has hashed source anchors.
- Bounded negative: no supported read-only firmware-body command was identified
  in audited call sites. No device command is sent. This is not proof that no
  undocumented firmware function exists.
- Unestablished: a small checksum delta localizes changed bytes, proves device
  personalization or locates a key; CC2540 hosts the DSP images; AES is the scan
  transform. Actual firmware bodies remain unavailable.

## During execution

Owner partial checkpoint: 123 isolated codec leads / 38,519 AES jobs and 18,480
integrity jobs with no match. No cross-acquisition codec lead at that checkpoint.
Do not treat a parser success as an intermediate or spectrum.

Final counts and verification will be appended on campaign completion. No
firmware acquisition, installation, reset, server request or correspondence occurs.

## Owner stage completed

- Header family: 57,800 AES configurations, 183 isolated codec leads, zero
  same-role cross-acquisition leads; 27,744 integrity configurations, zero matches.
- Delta family: 1,500 AES configurations, two isolated codec leads, no confirming
  lead; 720 integrity configurations, zero matches.
- Direct compression-only: no codec hit.
- Random keys: two isolated codec leads / 800 AES configurations; random bodies:
  two / 800. No cross-acquisition lead; both sets' 384 integrity configurations
  yielded zero matches.
- Interpretation: bounded negative for enumerated current-header derivations on
  the declared historical owner inputs. Not an exclusion of unavailable historical
  headers, custom codecs, different constructions or firmware-derived keys.

## Final contributor stage and assessment

- Contributor header family: 57,800 AES configurations, 192 isolated codec leads;
  27,744 integrity configurations, zero matches. One acquisition cannot establish
  independent structural confirmation or the ten-blob/three-group integrity gate.
- Contributor delta family: 1,500 AES configurations, four isolated leads;
  720 integrity configurations, zero matches. Direct compression-only: no hit.
- Contributor random keys: three isolated parses / 800 AES configurations; random
  bodies: two / 800. Integrity controls: 384 each, no matches.
- Complete: 180,266 jobs. Across both devices, 390 lead configurations yielded
  402 raw-deflate hits, consuming 4–68 bytes and leaving >=1,688 trailing bytes.
  No hit accounted for its stream tail. Zero owner cross-acquisition leads.
- Supported verification: input/evaluator/driver/helper hashes match; source and
  production snapshot unchanged; 263 socket-blocked research tests and 114
  unchanged production tests passed. No raw firmware bodies obtained.
- Remaining unknowns: unavailable historical header associations, different KDFs
  or framing, custom/headerless compression, firmware transform location and
  calibration. Negative results do not locate or exclude device-specific secrets.
