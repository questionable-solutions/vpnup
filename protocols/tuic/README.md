# TUIC

## Quick Start

> ⚠️ **Experimental.** The current image (`xchacha20/tuic-server`) does not include a Web UI.
> Client config must be written manually. A bundled-UI replacement is under evaluation.
> Use `vless-reality` or `wireguard` for production.

```bash
# 1. Deploy (accepts the experimental warning)
python setup.py

# Select protocol 4 (tuic), enter VPS IP, choose ports.
# A UUID and password are auto-generated.

# 2. Retrieve your credentials from .env:
cat .env | grep -E "TUIC_UUID|TUIC_PASSWORD|TUIC_PORT"

# 3. The container exposes:
#    - QUIC tunnel on TUIC_PORT (default 8443/udp)
#    - Web UI on TUIC_UI_PORT (default 8080) — if available

# 4. Client setup (manual — no UI config export yet):
#    Create a client config with the server IP, port, UUID, and password.
#    See https://github.com/EAimTY/tuic for client config format.
```

**Troubleshooting:** This protocol is not production-ready. Check back after a bundled-UI image is integrated.

---

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
