# Licensing and entitlement model

Recovered from `electron/access.ts` and `resources/native/manifest.json` in the
shipped AppImage.

## Two editions

| Edition | How it is detected | Save / export / clipboard |
|---|---|---|
| `lifetime` | native license service available **and** the signed license payload verifies with `state == "valid"` and an entitlement `vector-studio.licensed` with `enabled == true` and `limit_kind == "unlimited"` | allowed |
| `limited` | everything else | all three disabled |

`VectorAccess.snapshot()` returns:

```jsonc
{
  "edition": "lifetime" | "limited",
  "licenseState": "valid" | … | "none",
  "offlineExpiresAt": 1712345678 | null,
  "nativeAvailable": true | false,
  "capabilities": {
    "document.save":   true | false,
    "artwork.export":  true | false,
    "clipboard.external": true | false
  }
}
```

Gated features (constant `VECTOR_FEATURES`): `document.save`,
`artwork.export`, `clipboard.external`.

This is why `render` refuses to run on an unlicensed build: the broker calls
`requirePreview()`, which requires `artwork.export`.

## Native license service

The checks live in `resources/native/vector_native_engine.node` (a Rust N-API
addon built on `vello 0.6.0` + `wgpu 26.0.1`) and are reached through four
exports:

| Export | Purpose |
|---|---|
| `vectorLicenseBuildIdentity()` | must equal the pinned marker `TENZEN-LICENSE:vector-studio:1:<sha256 of the licence public key>` |
| `vectorLicenseAuthorize(context, feature)` | throws `{code:"LICENSE_REQUIRED"}` when the feature is not entitled |
| `vectorLicenseVerify(payload)` | verifies the signed license payload and returns `{verified, state, payload}` |
| `vectorSessionChallenge(stateDir, rotate)` | returns `{nonce, proof_time}` for the offline proof |

The build identity is pinned to a literal key id in the shipped bundle, so a
patched native engine fails the identity check with
`Vector native license identity mismatch`.

The verification context is:

```jsonc
{
  "license": "<token|null>",
  "device_id": "…",
  "device_public_key": "…",
  "proof": "…",
  "nonce": "…",
  "proof_time": 0,
  "state_dir": "…"
}
```

`offline_expires_at` inside the signed payload bounds how long a verified
license works without a network round trip.

## What this means for interoperability

The automation protocol itself is not gated: `capabilities`, `describe`,
`session.list`, `session.show`, `inspect`, `undo`, `redo` and `selection.set`
work on a `limited` install. The gated parts are export (`render` ->
`artwork.export`), saving to disk (`document.save`) and clipboard export
(`clipboard.external`).

This repository does not attempt to bypass any of these checks: it documents
them and provides a client that speaks the documented protocol.
