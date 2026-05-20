# Hysteria2

## Image
`toxxic/hysteria2:latest`

- **Source:** https://github.com/apernet/hysteria
- **Built-in UI:** [VERIFY] — The official Hysteria2 binary does **not** include a Web UI. This protocol requires a bundled-UI image (e.g., `mhsanaei/hysteria-dashboard`) to comply with the vpnUP UI contract. **Mark this protocol as experimental** until a verified image with an integrated management panel is identified and tested.

## DPI Evasion Status (Russia 2026)
| Capability            | Status                                            |
|-----------------------|---------------------------------------------------|
| Protocol fingerprint  | **Good** — QUIC-based, no clear Hysteria2 marker  |
| Adaptive congestion   | **Excellent** — Brutal congestion control         |
| UDP support           | **Native** — QUIC transport                       |
| Obfuscation           | **Good** — Optional obfuscation password          |

## Client Compatibility
| Platform | Client                        |
|----------|-------------------------------|
| Windows  | Hysteria GUI, Nekoray         |
| macOS    | Hysteria GUI                  |
| Linux    | Hysteria CLI, Nekoray         |
| iOS      | Shadowrocket, Streisand       |
| Android  | NekoBox, v2rayNG (limited)    |
