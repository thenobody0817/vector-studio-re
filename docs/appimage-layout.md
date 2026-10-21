# What is inside the AppImage

`Vector-Studio-0.1.11-linux-x64.AppImage` - 157 MB, Electron 44.5.1,
Chrome 152.0.7977.130, build target `x86_64-unknown-linux-gnu`.

Reproduce the layout with `tools/inspect_appimage.sh`.

## Top level

```
AppRun                     launcher (refuses --no-sandbox, needs user namespaces)
vector-studio              wrapper script -> vector-studio.bin
vector-studio.bin          the Electron binary
usr/lib/                   bundled shared libraries (libappindicator3, libgconf, …)
resources/
  app.asar                 69.6 MB - the whole application
  app.asar.unpacked/       native modules that cannot live inside the asar
  cli/vector               the "vector" CLI (stripped ELF, 562 KB)
  cli/version.json
  native/
    vector_native_engine.node   Rust N-API engine (vello + wgpu)
    manifest.json                engine manifest (ABI, protocol, build identity)
    third-party-licenses/        149 crate licence texts
```

## Inside `app.asar`

| Path | Size | What |
|---|---|---|
| `package.json` | 418 B | `@tenzen/vector-studio` 0.1.11, `private: true`, depends on `sharp` 0.34.5 |
| `dist-electron/electron/main.js` | 14.2 MB | Electron main process - **the original TypeScript sources are inline** |
| `dist-electron/electron/documentWorker.js` | 6.1 MB | document/editor worker |
| `dist-electron/electron/preload.js` | 9.9 KB | renderer bridge |
| `dist-electron/electron/recoveryWorker.js` | 680 KB | crash recovery |
| `dist-electron/electron/assetPreviewWorker.js` | 825 KB | asset preview worker |
| `dist-electron/i18n/*.json` | 23 locales | UI strings |
| `dist/index.html` + `dist/assets/*` | ~60 MB | the renderer (React + Vite) |
| `dist/engine/vector-kernels.wasm` | 290 KB | vector kernel module |
| `dist/assets/emscripten-module-*.wasm` | 1.0 MB | WASM glue for the text/PDF stack (plus `harfbuzz-*.wasm`) |
| `dist/assets/editor-*.js` | 13.4 MB | editor bundle |
| `dist/assets/_vector-catalog_<locale>.js` | 23 x ~500 KB | per-locale vector catalog |
| `dist/licenses/text-preview/` | 2 files | HarfBuzz 14.5.0 COPYING, fflate 0.8.3 LICENSE |
| `skills/automation/vector-artwork/` | 2 files | the shipped agent skill pack |

The bundle is an esbuild output that kept the module boundaries, each preceded
by a `// path/to/module.ts` marker. `tools/split_bundle.py` slices it back into
320 individual modules - that is how the protocol, the licensing model and the
integration manager were recovered.

## Native engine

`resources/native/manifest.json` describes the Rust engine:

```jsonc
{
  "licensing": { "policy": 1, "issuerKeyId": "2647ce7b…", "marker": "TENZEN-LICENSE:vector-studio:1:2647ce7b…" },
  "abi": 1, "protocol": 1, "product": "vector-studio",
  "target": "x86_64-unknown-linux-gnu", "profile": "release",
  "vello": "0.6.0", "wgpu": "26.0.1",
  "solidPaint": "normalized-float-srgb-with-legacy-hex",
  "linearGradientFill": { "colorSpace": "srgb", "alphaInterpolation": "premultiplied-constant-stop-alpha", … },
  "source": { "files": [ … 241 entries … ] },
  "builtAt": …, "rustc": …, "notices": …, "sha256": …
}
```

The 241 source entries reveal the internal package layout:
`packages/vector-engine` (233 files), `packages/photo-engine` (5),
`packages/suite-license` (3).

`resources/native/third-party-licenses/` carries the licence text of 149 crates
(`ash`, `wgpu`, `vello`, `naga`, `tiny-skia`, …).

## The CLI

`resources/cli/vector` is a stripped ELF binary that implements the same
operations over HTTP plus an MCP stdio server. Its help text:

```
Vector Studio CLI

capabilities | describe | doctor | session list/show
inspect | execute OPERATION | render
integrations list/install/remove/test | skills list/import/export/remove | mcp
```

Exit codes: `0` success, `1` operation error, `2` transport/input error.
