# Hysteria2

## Quick Start

> ⚠️ **Experimental.** The current image (`toxxic/hysteria2`) does not include a Web UI.
> Client config must be written manually or managed via CLI. A bundled-UI replacement
> is under evaluation. Use `vless-reality` or `wireguard` for production.

```bash
# 1. Deploy (accepts the experimental warning)
python setup.py

# Select protocol 3 (hysteria2), enter VPS IP, choose ports.
# An obfuscation password is auto-generated.

# 2. Retrieve your credentials from .env:
cat .env | grep -E "HYSTERIA|ADMIN_PASSWORD"

# 3. The container exposes:
#    - UDP tunnel on HYSTERIA_PORT (default 8443)
#    - Web UI on HYSTERIA_UI_PORT (default 8080) — if available

# 4. Client setup (manual — no UI config export yet):
#    Create a client config JSON referencing the server IP, port, and obfs password.
#    See https://hysteria.network/docs/ for config syntax.
```

**Troubleshooting:** This protocol is not production-ready. Check back after a bundled-UI image is integrated.

---

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
