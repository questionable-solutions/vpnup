# WireGuard via wg-easy

## Image
`ghcr.io/wg-easy/wg-easy:14`

- **Source:** https://github.com/wg-easy/wg-easy
- **Tag policy:** Pinned to major version 14 for stability. Check upstream for latest patch.
- **Built-in UI:** Yes — Web dashboard on mapped `WG_UI_PORT` (default 51821).

## Default Credentials
- **Username:** Not applicable — single-password authentication.
- **Password:** Set via `ADMIN_PASSWORD` in `.env`. Displayed once after `setup.py` completes.
- **First run:** The Web UI is immediately available. The password is the one injected at deploy time.

## Client Configuration
- QR codes and `.conf` file downloads are available directly from the Web UI.
- Navigate to `http://<VPN_HOST>:<WG_UI_PORT>` after deployment.
- Each client peer can be created/revoked through the dashboard.

## DPI Evasion Status (Russia 2026)
| Capability            | Status                                          |
|-----------------------|-------------------------------------------------|
| Protocol fingerprint  | **Poor** — WireGuard handshake is well-known    |
| Port-based blocking   | Mitigated by using non-default `WG_PORT`        |
| Deep packet inspection| WireGuard is trivially detectable               |
| Obfuscation           | None built-in                                   |

**Recommendation:** Use WireGuard as a **baseline fallback** only. In restrictive networks, prefer `vless-reality` or `hysteria2`. WireGuard may work in environments where DPI is not aggressively deployed or when combined with an external obfuscation layer (not provided by this project).

## Client Compatibility
| Platform     | Client                                    |
|--------------|-------------------------------------------|
| Windows      | WireGuard official client                  |
| macOS        | WireGuard official client                  |
| Linux        | `wireguard-tools` + NetworkManager         |
| iOS          | WireGuard App Store client                 |
| Android      | WireGuard Google Play client               |

## Port Reference
| Port          | Protocol | Purpose              |
|---------------|----------|----------------------|
| `WG_PORT`     | UDP      | WireGuard tunnel     |
| `WG_UI_PORT`  | TCP      | Management Web UI    |

## Security Notes
- The container runs with `NET_ADMIN` and `SYS_MODULE` capabilities — required for kernel WireGuard.
- The Web UI is served over **HTTP** (no built-in TLS). If exposing to the internet, place it behind a reverse proxy with TLS termination.
- All persistent data is stored in `./wireguard-data/` on the host.
