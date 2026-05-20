# vpnUP

## 1. Project Overview
Automate deployment of a personal VPN server via a single setup script. The project assumes pre-configured VPS security (SSH key-only, non-root user) and Docker installation. After `git clone`, the user runs a CLI script that interactively collects parameters, generates a `.env` file, and starts `docker compose`. Management and configuration download are handled exclusively by built-in Web UIs provided by the selected VPN framework images. Custom UI development is strictly prohibited.

## 2. Architecture & Structure
```
vpn-deploy/
├── setup.py                  # Main CLI entrypoint (Python)
├── docker-compose.yml        # Protocol-agnostic base compose file
├── .env.example              # Template for environment variables
├── protocols/                # Isolated protocol implementations
│   ├── vless-reality/
│   │   ├── compose.override.yml
│   │   ├── config.template
│   │   └── README.md
│   ├── tuic/
│   │   ├── compose.override.yml
│   │   └── README.md
│   ├── hysteria2/
│   │   ├── compose.override.yml
│   │   └── README.md
│   └── wireguard/
│       ├── compose.override.yml
│       └── README.md
├── tests/                    # Unit/integration tests for setup logic
└── AGENTS.md                 # This file
```

## 3. Protocol Isolation & Bundled UI Contract
Each directory under `protocols/` must be fully self-contained. Required artifacts per protocol:
- `compose.override.yml`: Defines the protocol service using an official or well-maintained community image that includes both the VPN engine and a management Web UI. Must not duplicate base services. Must expose the UI port and map configuration directories.
- `config.template`: Jinja2/Python template for runtime variables (ports, credentials, domain/IP, protocol-specific flags).
- `README.md`: Deployment notes, default UI credentials, known DPI evasion status, and client compatibility.

**Integration Rule:** The setup script dynamically selects the protocol directory, renders `compose.override.yml` to the project root, applies `.env` variables, and executes `docker compose -f docker-compose.yml -f docker-compose.override.yml up -d`. No cross-protocol dependencies are allowed.

## 4. Setup Script Behavior (`setup.py`)
- **CLI Framework:** `click` or `typer`. Strict typing, explicit validation.
- **Flow:** 
  1. Check for existing `.env`. If present, skip prompts unless `--force` is provided.
  2. Prompt for: public IP/domain, protocol selection, UI admin credentials (or auto-generate), required ports.
  3. Validate inputs against protocol constraints and port availability.
  4. Render `.env` from `.env.example`.
  5. Generate protocol-specific configs if required by the image.
  6. Execute `docker compose pull` and `docker compose up -d`.
  7. Print access URL, admin credentials, and QR/config download instructions to stdout.
- **Idempotency:** Safe to re-run. Logs to `setup.log`. Non-zero exit on validation or compose failure.
- **Security:** Secrets generated at runtime, never cached. Enforce `umask 077` for `.env` and config directories.

## 5. Bundled Web UI Integration Rules
- **No Custom Development:** Agents must not implement backend/frontend code for management interfaces.
- **Image Selection Criteria:** Prioritize actively maintained images with built-in dashboards (e.g., `ghcr.io/wg-easy/wg-easy`, `ghcr.io/azumi67/3x-ui`, `mhsanaei/hysteria-dashboard`, or equivalent). Images must support non-root execution, healthchecks, and explicit credential injection via environment variables.
- **Credential Handling:** If the image requires initial password setup, the script must inject it via `.env` or first-run API call. Print credentials exactly once during successful deployment.
- **Access Abstraction:** The script must resolve the final UI URL (`http(s)://<IP>:<PORT>`) and output it post-deployment. No hardcoded ports in the base compose file.

## 6. Protocol Recommendations (Russia 2026 Context)
Prioritize protocols with native TLS/QUIC encapsulation, active DPI evasion, and maintained client ecosystems:
- `vless-reality` (Xray-core + 3x-ui/Marzban-based image): High resilience, no SNI dependency, regularly updated.
- `hysteria2`: UDP-based, adaptive congestion control, strong against DPI, paired with official dashboard image.
- `tuic`: QUIC multiplexing, low latency, requires image with integrated management panel.
- `wireguard` (wg-easy): Baseline fallback. Document limitations in restrictive networks.

**Note:** DPI rules evolve. Implement a `--check-ports` or `--verify-image` hook to validate container health and UI reachability post-start. Avoid deprecated or unmaintained panels.

## 7. AI Agent Directives
- **Package Management:** Use `uv` for all Python dependency operations. Install with `uv pip install --system <pkg>`. Do not use bare `pip`.
- **Code Quality:** PEP-8, strict typing, `ruff`/`black` compatible. Stateless setup logic.
- **Docker:** Official or audited base images only. Compose v2 syntax. Run as non-root where possible. Explicit resource limits.
- **Error Handling:** Graceful degradation, explicit exit codes, user-readable messages. Suppress raw tracebacks in production flow.
- **Testing:** `pytest` suite for env validation, config rendering, and compose override generation. Mock subprocess/docker calls.
- **Documentation:** Inline comments for non-obvious logic. `README.md` per protocol must include exact image tag, default UI credentials, and DPI evasion notes.

## 8. Deliverables Checklist
- [ ] Project structure matches specification
- [ ] `setup.py` with protocol selection, `.env` generation, credential handling, and compose orchestration
- [ ] Protocol directories fulfilling isolation contract and referencing bundled-UI images
- [ ] `docker-compose.yml` + dynamic override mechanism
- [ ] `.env.example` with validation schema and security defaults
- [ ] `tests/` with ≥80% coverage on setup logic and compose generation
- [ ] Post-deployment output includes UI URL, credentials, and next steps
- [ ] CI-ready configuration (GitHub Actions or equivalent)
