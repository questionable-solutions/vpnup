# vpnUP

**One command.** Your own VPN server. Built-in management panel. No custom code.

```bash
git clone https://github.com/example/vpnup.git && cd vpnup
python setup.py
```

---

## What This Is

A single Python script that deploys a personal VPN server on any Docker-capable VPS.
It asks a few questions (IP, protocol, ports), generates a hardened `.env`, pulls the right
Docker image, and starts everything. Management — creating clients, downloading configs,
generating QR codes — happens entirely through the **built-in Web UI** of the VPN image.
No custom dashboards. No magic.

**Supported protocols:** WireGuard, VLESS + Reality, Hysteria2, TUIC.

---

## Quick Start

**Prerequisites:** A Linux VPS with Docker Engine (v2 compose plugin) installed.
SSH key-only authentication. Non-root user with `docker` group membership.

```bash
# 1. Clone
git clone https://github.com/example/vpnup.git && cd vpnup

# 2. Deploy (interactive)
python setup.py

#    You'll be asked:
#    - Public IP or domain of your VPS
#    - Protocol (1-4)
#    - Admin credentials for the Web UI (or auto-generate)
#    - Ports (accept defaults or customize)
#
#    After images are pulled and containers start, the script prints:
#    - Web UI URL
#    - Username / password

# 3. Open the Web UI, create clients, share configs

# 4. Verify health at any time
python setup.py --verify-image

# 5. Re-deploy with new settings
python setup.py --force
```

---

## Protocol Selection Guide

| # | Protocol | DPI Resistance | Web UI | Status |
|---|----------|---------------|--------|--------|
| 1 | [WireGuard](protocols/wireguard/README.md) | Low | ✅ wg-easy | Stable |
| 2 | [VLESS + Reality](protocols/vless-reality/README.md) | **High** | ✅ 3x-ui | Stable |
| 3 | [Hysteria2](protocols/hysteria2/README.md) | Good | ❌ [VERIFY] | Experimental |
| 4 | [TUIC](protocols/tuic/README.md) | Good | ❌ [VERIFY] | Experimental |

**If you're in Russia or another restrictive network**, pick **VLESS + Reality** (protocol #2).
It's the only option that reliably bypasses modern DPI. WireGuard is trivially blocked.

**If you just want a simple VPN and aren't worried about censorship**, pick **WireGuard** (protocol #1).
It's faster, simpler, and has native clients on every platform.

---

## DPI Evasion — Comprehensive Comparison

*Evaluated against the Russian 2026 DPI threat model: protocol fingerprinting,
TLS inspection, SNI filtering, active probing, and port-based blocking.*

| Capability | WireGuard | VLESS + Reality | Hysteria2 | TUIC |
|------------|-----------|-----------------|-----------|------|
| **Protocol fingerprint** | Poor — well-known handshake | **Excellent** — no handshake signature | Good — QUIC-based, no clear marker | Good — QUIC-based, multiplexed |
| **TLS fingerprint** | N/A (no TLS) | **Excellent** — piggybacks real cert | Good — standard QUIC TLS | Good — standard QUIC TLS |
| **SNI-based blocking** | N/A | **Bypassed** — uses dest site's SNI | Vulnerable without domain fronting | Vulnerable without domain fronting |
| **Active probing resistance** | None | **Mitigated** — shortId required | None built-in | None built-in |
| **Port-based blocking** | Mitigated (custom port) | Mitigated (custom port) | Mitigated (custom port) | Mitigated (custom port) |
| **Obfuscation layer** | None | Reality (mimics TLS to CDN) | Optional password obfuscation | QUIC itself provides cover |
| **UDP support** | Native | Via Xray | Native (QUIC) | Native (QUIC) |
| **Congestion control** | Standard | Standard | **Brutal** (adaptive, aggressive) | Standard |
| **Multiplexing** | No | Via Xray (mux) | QUIC native | **QUIC native** |
| **Maintained client ecosystem** | Excellent (official apps) | **Excellent** (v2rayN/NG, Shadowrocket) | Good (GUI + CLI) | Limited (CLI-heavy) |
| **Overall DPI resilience** | **Low** | **Very High** | High | Medium-High |

### How Reality Works (Why VLESS Beats DPI)

Most DPI systems fingerprint TLS by checking the ClientHello and ServerHello.
Reality doesn't generate its own TLS — it **forwards** the ServerHello from a real
HTTPS site (e.g., `www.microsoft.com:443`). To the DPI box, your VPN traffic is
indistinguishable from someone browsing Microsoft's CDN. The shortId acts as
a shared secret that prevents active probing: a scanner won't get a valid response
unless it knows the shortId.

### WireGuard Limitations

WireGuard has a distinctive 4-way handshake. DPI hardware from Sandvine, Procera,
and domestic Russian vendors (e.g., RDP.RU) fingerprint it trivially. In 2024-2026
Russian networks, WireGuard is blocked at the transport layer within seconds of the
first handshake packet. Use it only as a fallback or in non-restrictive environments.

---

## Architecture

```
vpnup/
├── setup.py                         # CLI orchestrator (typer, Python 3.10+)
├── docker-compose.yml               # Shared network definition
├── .env.example                     # All tunables with documentation
├── protocols/
│   ├── wireguard/                   # ghcr.io/wg-easy/wg-easy:14
│   │   ├── compose.override.yml
│   │   └── README.md
│   ├── vless-reality/               # ghcr.io/azumi67/3x-ui:latest
│   │   ├── compose.override.yml
│   │   ├── config.template
│   │   └── README.md
│   ├── hysteria2/                   # ⚠️ experimental
│   │   ├── compose.override.yml
│   │   └── README.md
│   └── tuic/                        # ⚠️ experimental
│       ├── compose.override.yml
│       └── README.md
└── tests/                           # pytest, 93% coverage
```

**How it works:** `setup.py` copies the selected protocol's `compose.override.yml`
to the project root, renders `.env` from the template, and runs
`docker compose -f docker-compose.yml -f docker-compose.override.yml up -d`.
Protocol directories never reference each other. Swapping protocols is a re-run
with `--force`.

---

## Requirements

| Dependency | Version | Notes |
|------------|---------|-------|
| Python | ≥ 3.10 | |
| Docker Engine | ≥ 24 | with compose v2 plugin |
| `openssl` | any | only for vless-reality (x25519 keygen) |
| OS | Linux | tested on Debian 12, Ubuntu 22.04+ |

Python packages (installed automatically by `uv`):

| Package | Purpose |
|---------|---------|
| `typer` | CLI framework |
| `pytest` | test suite (dev) |
| `ruff` | linting (dev) |

---

## Security

- **Secrets never touch disk unencrypted** outside `.env`, which is created with `umask 077` (owner read/write only).
- Admin passwords: 24-char cryptographically random (`secrets` module), shell-safe alphabet.
- Reality x25519 keys generated via `openssl genpkey` at deploy time, stored in `.env` only.
- `.env` is in `.gitignore`. Only `.env.example` (template) is committed.
- Containers run with explicit CPU/memory limits. WireGuard containers require `NET_ADMIN` + `SYS_MODULE` — inherent to kernel WireGuard.
- Management UIs are served over HTTP by default. For production internet exposure, place behind a reverse proxy with TLS termination or use SSH tunneling (`ssh -L`).

---

## Testing

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest tests/ --cov=setup
```

100 tests, 93% coverage on validation, rendering, compose generation, secrets, and CLI flows.
All Docker/subprocess calls are mocked.

---

## License

MIT

---

## Status

| Protocol | Status | Notes |
|----------|--------|-------|
| WireGuard | ✅ Production | ghcr.io/wg-easy/wg-easy:14 |
| VLESS + Reality | ✅ Production | ghcr.io/azumi67/3x-ui:latest; primary recommendation for restricted networks |
| Hysteria2 | ⚠️ Experimental | Needs verified bundled-UI image |
| TUIC | ⚠️ Experimental | Needs verified bundled-UI image |
| CLI & Tests | ✅ Complete | 100 tests, 93% coverage |

---

## Links

- [AGENTS.md](AGENTS.md) — Full technical specification and AI agent directives
- [WireGuard README](protocols/wireguard/README.md) — Deployment notes, DPI status, client list
- [VLESS + Reality README](protocols/vless-reality/README.md) — Deployment notes, post-deploy setup, DPI evasion deep-dive
- [Hysteria2 README](protocols/hysteria2/README.md) — Experimental notes, DPI status
- [TUIC README](protocols/tuic/README.md) — Experimental notes, DPI status
