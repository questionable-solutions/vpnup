# TUIC

## Image
`xchacha20/tuic-server:latest`

- **Source:** https://github.com/EAimTY/tuic
- **Built-in UI:** [VERIFY] — The official TUIC server does **not** include a Web UI. This protocol requires a bundled-UI image to comply with the vpnUP UI contract. Community-wrapped TUIC + dashboard images exist but have not been vetted. **Mark as experimental** until a verified image is identified.

## DPI Evasion Status (Russia 2026)
| Capability            | Status                                          |
|-----------------------|-------------------------------------------------|
| Protocol fingerprint  | **Good** — QUIC-based, multiplexed              |
| QUIC multiplexing     | **Excellent** — Native connection multiplexing  |
| UDP support           | **Native** — QUIC transport                     |
| Obfuscation           | Limited — QUIC itself provides some cover       |

## Client Compatibility
| Platform | Client                  |
|----------|-------------------------|
| Windows  | TUIC Client (CLI)       |
| macOS    | TUIC Client (CLI)       |
| Linux    | TUIC Client (CLI)       |
| iOS      | Shadowrocket, Streisand |
| Android  | NekoBox                 |
