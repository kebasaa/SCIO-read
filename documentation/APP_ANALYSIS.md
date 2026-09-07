# Decompiled SCIO app data-path analysis

## Result

The inspected Android applications transport scan blobs to the cloud and parse
spectra returned by the cloud. No local raw-blob-to-spectrum implementation or
SCIO-specific native decoding library was found.

## Verified path in the 2017 Researcher SDK

The source locations below are under the decompiled tree
`<SCIO_DECOMPILED_ROOT>`.

- `ScioInternalDevice.handleScan2` assigns response 0 to `sampleDark`, response
  1 to `sample`, and response 2 to `sampleGradient`.
- The calibration handler performs the same assignment and stores it as the
  white reference.
- `ResponseCommand.getDataAsBase64` calls Android
  `Base64.encodeToString(this.data, 0)` directly. There is no intervening
  transform.
- `ScioPhoneInternalDevice` independently uses message 1 as dark, message 2 as
  sample and message 3 as gradient.
- `ScioInternalCloud.getSpectrum` reads `spectrum` and `wavelengths` from the
  server response and constructs the returned spectrum.

The same architecture is present in the inspected later Consumer and Lab app
variants: raw triplets go outward and wavelength/value arrays come back.

## Native and packaged artifacts

- APK native-library inventories contain the generic GIF library but no
  SCIO-specific spectral decoder.
- No complete `dsp_op`, centers, bins, dead-pixel or pixel-count table body was
  found packaged in the inspected applications.
- Firmware-upgrade code accepts server-supplied Base64 files, strips a four-byte
  checksum prefix and sends the remaining body to the device.
- A preference described as a key “per Aptina ID” is a preferences namespace;
  it is not evidence of a cryptographic key.
- AES strings in generic TLS dependencies are unrelated to the scan path unless
  further call-path evidence connects them.

## Consequence

There is no app-side function to port. Offline recovery must identify the
device/server transform from captures or recover a relevant local artifact.
Encryption, key derivation and key location remain hypotheses.
