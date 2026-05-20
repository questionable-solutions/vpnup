#!/usr/bin/env python3
"""vpnUP — Single-command VPN server deployment orchestrator.

Manages interactive configuration collection, .env generation, protocol-specific
config rendering, and docker compose orchestration. All management is delegated
to the bundled Web UIs of the selected VPN images.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import re
import secrets
import shutil
import socket
import string
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT: Path = Path(__file__).resolve().parent
PROTOCOLS_DIR: Path = PROJECT_ROOT / "protocols"
ENV_EXAMPLE: Path = PROJECT_ROOT / ".env.example"
ENV_FILE: Path = PROJECT_ROOT / ".env"
OVERRIDE_FILE: Path = PROJECT_ROOT / "docker-compose.override.yml"
LOG_FILE: Path = PROJECT_ROOT / "setup.log"

PASSWORD_LENGTH: int = 24
SHORT_ID_LENGTH: int = 8  # hex characters for Reality shortId

SUPPORTED_PROTOCOLS: list[str] = ["wireguard", "vless-reality", "hysteria2", "tuic"]

# Protocols that require config.template rendering
PROTOCOLS_WITH_TEMPLATES: set[str] = {"vless-reality"}

# Protocols with [VERIFY] image status — warn the user
EXPERIMENTAL_PROTOCOLS: set[str] = {"hysteria2", "tuic"}


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def _setup_logging() -> None:
    """Configure file + console logging. File receives DEBUG, console INFO."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)-8s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    # Keep console at INFO
    for h in logging.getLogger().handlers:
        if isinstance(h, logging.StreamHandler) and h.stream is sys.stdout:
            h.setLevel(logging.INFO)


logger = logging.getLogger("vpnup")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class Protocol(str, Enum):
    WIREGUARD = "wireguard"
    VLESS_REALITY = "vless-reality"
    HYSTERIA2 = "hysteria2"
    TUIC = "tuic"


@dataclass
class DeployConfig:
    """All configuration parameters across every supported protocol.

    Only the subset relevant to the selected protocol is prompted for.
    Secrets (passwords, keys) are generated at runtime and never cached
    outside of .env.
    """

    host: str = ""
    protocol: Protocol = Protocol.WIREGUARD

    # Shared credentials
    admin_username: str = "admin"
    admin_password: str = ""

    # WireGuard
    wg_port: int = 51820
    wg_ui_port: int = 51821
    wg_default_dns: str = "1.1.1.1,1.0.0.1"
    wg_allowed_ips: str = "0.0.0.0/0"
    wg_mtu: int = 1420

    # VLESS + Reality
    xui_port: int = 2053
    vless_port: int = 443
    reality_dest: str = "www.microsoft.com:443"
    reality_server_names: str = "www.microsoft.com,www.google.com"
    reality_private_key: str = ""
    reality_public_key: str = ""
    reality_short_id: str = ""

    # Hysteria2
    hysteria_port: int = 8443
    hysteria_ui_port: int = 8080
    hysteria_obfs: str = ""
    hysteria_cert_domain: str = ""

    # TUIC
    tuic_port: int = 8443
    tuic_ui_port: int = 8080
    tuic_cert_domain: str = ""
    tuic_uuid: str = ""
    tuic_password: str = ""

    # UI port mapping — keyed by protocol
    _UI_PORT_MAP: dict[Protocol, str] = field(
        default_factory=lambda: {
            Protocol.WIREGUARD: "wg_ui_port",
            Protocol.VLESS_REALITY: "xui_port",
            Protocol.HYSTERIA2: "hysteria_ui_port",
            Protocol.TUIC: "tuic_ui_port",
        },
        repr=False,
        hash=False,
        compare=False,
    )

    @property
    def ui_port_attr(self) -> str:
        """Return the dataclass attribute name for the active protocol's UI port."""
        return self._UI_PORT_MAP.get(self.protocol, "")

    @property
    def ui_port_value(self) -> int:
        """Return the active protocol's UI port value."""
        attr = self.ui_port_attr
        return int(getattr(self, attr, 0))


# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------


def _secure_umask() -> None:
    """Set umask to 077 so files are created with owner-only permissions."""
    os.umask(0o077)


def generate_password(length: int = PASSWORD_LENGTH) -> str:
    """Generate a cryptographically random password.

    Uses the full printable ASCII set excluding whitespace and shell-special
    characters (backslash, backtick, dollar, single/double quotes).
    """
    alphabet = string.ascii_letters + string.digits + "!@#%^&*()-_=+[]{}|;:,.<>?/~"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_hex_id(length: int = SHORT_ID_LENGTH) -> str:
    """Generate a random hex string (e.g., for Reality shortId)."""
    return secrets.token_hex(length // 2)[:length]


def generate_reality_keys() -> tuple[str, str]:
    """Generate an x25519 key pair for Reality via openssl.

    Returns (private_key, public_key) as PEM-encoded strings without headers.
    Openssl must be available on the system PATH.
    """
    try:
        priv = subprocess.run(
            ["openssl", "genpkey", "-algorithm", "x25519"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        pub = subprocess.run(
            ["openssl", "pkey", "-pubout"],
            input=priv.stdout,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        # Strip PEM headers/footers and whitespace
        priv_key = "".join(
            line for line in priv.stdout.strip().split("\n") if not line.startswith("-----")
        )
        pub_key = "".join(
            line for line in pub.stdout.strip().split("\n") if not line.startswith("-----")
        )
        return priv_key, pub_key
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        logger.error("Failed to generate Reality keys via openssl: %s", exc)
        raise SystemExit(1) from exc


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class ValidationError(Exception):
    """Raised when user input fails validation."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def validate_host(value: str) -> str:
    """Validate a public IP address or domain name.

    Returns the normalized value on success. Raises ValidationError on failure.
    """
    value = value.strip()
    if not value:
        raise ValidationError("Host must not be empty.")

    # Check if it's an IP address
    try:
        addr = ipaddress.ip_address(value)
        if addr.is_loopback:
            raise ValidationError(f"Loopback address not allowed: {value}")
        if addr.is_multicast:
            raise ValidationError(f"Multicast address not allowed: {value}")
        if addr.is_unspecified:
            raise ValidationError(f"Unspecified address not allowed: {value}")
        if isinstance(addr, ipaddress.IPv4Address) and addr.is_private:
            logger.warning("Using private IPv4 address %s — ensure clients can reach it.", value)
        return str(addr)
    except ValueError:
        pass  # Not an IP — try domain validation

    # Basic domain name validation
    domain_pattern = re.compile(
        r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$"
    )
    if domain_pattern.match(value):
        return value

    raise ValidationError(f"Invalid host: '{value}'. Must be a valid IP address or domain name.")


def validate_port(value: str | int, allow_privileged: bool = True) -> int:
    """Validate a port number is in range.

    Args:
        value: The port to validate.
        allow_privileged: If False, disallow ports < 1024.

    Returns the port as int. Raises ValidationError.
    """
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"Port must be an integer, got: {value}") from exc

    min_port = 1 if allow_privileged else 1024
    if not (min_port <= port <= 65535):
        raise ValidationError(f"Port {port} not in range {min_port}-65535.")

    return port


def check_port_available(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a TCP port is available on the given host.

    Returns True if the port is free, False if already bound.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        sock.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def validate_protocol(value: str) -> str:
    """Validate protocol selection against supported protocols."""
    value = value.strip().lower()
    if value not in SUPPORTED_PROTOCOLS:
        raise ValidationError(
            f"Unsupported protocol: '{value}'. Choose from: {', '.join(SUPPORTED_PROTOCOLS)}"
        )
    return value


# ---------------------------------------------------------------------------
# Interactive prompts
# ---------------------------------------------------------------------------


def _prompt_host(default: str = "") -> str:
    """Prompt for the public IP or domain name."""
    while True:
        prompt = f"Public IP or domain{f' [{default}]' if default else ''}: "
        raw = typer.prompt(prompt, default=default, show_default=False)
        try:
            return validate_host(raw)
        except ValidationError as exc:
            typer.echo(f"  ❌ {exc.message}", err=True)


def _prompt_protocol() -> Protocol:
    """Prompt for protocol selection."""
    typer.echo("\nAvailable protocols:")
    for i, name in enumerate(SUPPORTED_PROTOCOLS, 1):
        marker = " ⚠️ [EXPERIMENTAL]" if name in EXPERIMENTAL_PROTOCOLS else ""
        typer.echo(f"  {i}. {name}{marker}")
    typer.echo("")

    while True:
        raw = typer.prompt(
            "Select protocol",
            default="1",
            show_default=False,
        )
        # Accept name or number
        try:
            if raw.isdigit():
                idx = int(raw) - 1
                if 0 <= idx < len(SUPPORTED_PROTOCOLS):
                    name = SUPPORTED_PROTOCOLS[idx]
                else:
                    typer.echo(
                        f"  ❌ Number out of range (1-{len(SUPPORTED_PROTOCOLS)}).",
                        err=True,
                    )
                    continue
            else:
                name = validate_protocol(raw)
            proto = Protocol(name)

            if name in EXPERIMENTAL_PROTOCOLS:
                typer.echo(f"  ⚠️  '{name}' is marked experimental — bundled UI not yet verified.")
                if not typer.confirm("  Continue anyway?"):
                    continue

            return proto
        except ValidationError as exc:
            typer.echo(f"  ❌ {exc.message}", err=True)


def _prompt_credentials(config: DeployConfig) -> None:
    """Prompt for admin credentials or auto-generate."""
    typer.echo("\n--- Admin Credentials ---")
    config.admin_username = (
        typer.prompt("Web UI username", default="admin", show_default=True).strip() or "admin"
    )

    if typer.confirm("Set a custom admin password?", default=False):
        while True:
            pw = typer.prompt("Admin password", hide_input=True)
            if len(pw) < 8:
                typer.echo("  ❌ Password must be at least 8 characters.", err=True)
                continue
            pw2 = typer.prompt("Confirm password", hide_input=True)
            if pw != pw2:
                typer.echo("  ❌ Passwords do not match.", err=True)
                continue
            config.admin_password = pw
            break
    else:
        config.admin_password = generate_password()
        typer.echo("  🔑 Auto-generated admin password (saved to .env)")


def _prompt_ports(config: DeployConfig) -> None:
    """Prompt for protocol-specific ports with availability checks."""
    typer.echo("\n--- Port Configuration ---")

    if config.protocol == Protocol.WIREGUARD:
        _prompt_single_port("WireGuard UDP port", "wg_port", config, default=51820)
        _prompt_single_port("Web UI port", "wg_ui_port", config, default=51821)
    elif config.protocol == Protocol.VLESS_REALITY:
        _prompt_single_port("VLESS inbound port", "vless_port", config, default=443)
        _prompt_single_port("3x-ui panel port", "xui_port", config, default=2053)
    elif config.protocol == Protocol.HYSTERIA2:
        _prompt_single_port("Hysteria2 UDP port", "hysteria_port", config, default=8443)
        _prompt_single_port("Web UI port", "hysteria_ui_port", config, default=8080)
    elif config.protocol == Protocol.TUIC:
        _prompt_single_port("TUIC QUIC port", "tuic_port", config, default=8443)
        _prompt_single_port("Web UI port", "tuic_ui_port", config, default=8080)


def _prompt_single_port(label: str, attr: str, config: DeployConfig, default: int) -> None:
    """Prompt for a single port, validate, and check availability."""
    while True:
        raw = typer.prompt(f"{label}", default=str(default), show_default=True)
        try:
            port = validate_port(raw)
            setattr(config, attr, port)
            if not check_port_available(port):
                typer.echo(f"  ⚠️  Port {port} appears to be in use.", err=True)
                if not typer.confirm("  Use it anyway?", default=False):
                    continue
            break
        except ValidationError as exc:
            typer.echo(f"  ❌ {exc.message}", err=True)


# ---------------------------------------------------------------------------
# .env rendering
# ---------------------------------------------------------------------------


def _build_template_context(config: DeployConfig) -> dict[str, str]:
    """Build the variable substitution map for .env.example rendering.

    Every {{PLACEHOLDER}} in .env.example must have an entry here. Variables
    irrelevant to the selected protocol are set to their defaults (empty string
    for secrets that should be regenerated, or sensible defaults for ports).
    """
    return {
        "VPN_HOST": config.host,
        "VPN_PROTOCOL": config.protocol.value,
        "ADMIN_USERNAME": config.admin_username,
        "ADMIN_PASSWORD": config.admin_password,
        # WireGuard
        "WG_PORT": str(config.wg_port),
        "WG_UI_PORT": str(config.wg_ui_port),
        "WG_DEFAULT_DNS": config.wg_default_dns,
        "WG_ALLOWED_IPS": config.wg_allowed_ips,
        "WG_MTU": str(config.wg_mtu),
        # VLESS + Reality
        "XUI_PORT": str(config.xui_port),
        "VLESS_PORT": str(config.vless_port),
        "REALITY_DEST": config.reality_dest,
        "REALITY_SERVER_NAMES": config.reality_server_names,
        "REALITY_PRIVATE_KEY": config.reality_private_key,
        "REALITY_PUBLIC_KEY": config.reality_public_key,
        "REALITY_SHORT_ID": config.reality_short_id,
        # Hysteria2
        "HYSTERIA_PORT": str(config.hysteria_port),
        "HYSTERIA_UI_PORT": str(config.hysteria_ui_port),
        "HYSTERIA_OBFS": config.hysteria_obfs,
        "HYSTERIA_CERT_DOMAIN": config.hysteria_cert_domain,
        # TUIC
        "TUIC_PORT": str(config.tuic_port),
        "TUIC_UI_PORT": str(config.tuic_ui_port),
        "TUIC_CERT_DOMAIN": config.tuic_cert_domain,
        "TUIC_UUID": config.tuic_uuid,
        "TUIC_PASSWORD": config.tuic_password,
    }


def _render_env(
    context: dict[str, str],
    template_path: Path | None = None,
    output_path: Path | None = None,
) -> None:
    """Render .env from .env.example by substituting {{PLACEHOLDER}} markers."""
    if template_path is None:
        template_path = ENV_EXAMPLE
    if output_path is None:
        output_path = ENV_FILE
    if not template_path.exists():
        logger.error("Template file not found: %s", template_path)
        raise SystemExit(1)

    template = template_path.read_text(encoding="utf-8")

    def _replace(match: re.Match) -> str:
        key = match.group(1)
        return context.get(key, match.group(0))

    rendered = re.sub(r"\{\{(\w+)\}\}", _replace, template)

    _ = _secure_umask()
    output_path.write_text(rendered, encoding="utf-8")
    logger.info(".env written to %s", output_path)


# ---------------------------------------------------------------------------
# Protocol config rendering
# ---------------------------------------------------------------------------


def _render_protocol_config(config: DeployConfig) -> None:
    """Render protocol-specific config.template if the protocol requires one."""
    proto_dir = PROTOCOLS_DIR / config.protocol.value
    template_path = proto_dir / "config.template"

    if config.protocol.value not in PROTOCOLS_WITH_TEMPLATES:
        logger.debug("No config.template needed for %s.", config.protocol.value)
        return

    if not template_path.exists():
        logger.warning("config.template not found at %s — skipping.", template_path)
        return

    logger.info("Rendering protocol config from %s ...", template_path)
    template = template_path.read_text(encoding="utf-8")

    ctx = _build_template_context(config)
    rendered = re.sub(r"\{\{(\w+)\}\}", lambda m: ctx.get(m.group(1), m.group(0)), template)

    output_dir = PROJECT_ROOT / f"{config.protocol.value}-data"
    output_dir.mkdir(parents=True, exist_ok=True)
    _ = _secure_umask()
    output_file = output_dir / "config.json"
    output_file.write_text(rendered, encoding="utf-8")
    logger.info("Protocol config written to %s", output_file)


# ---------------------------------------------------------------------------
# Compose override
# ---------------------------------------------------------------------------


def _render_override(config: DeployConfig) -> None:
    """Copy the selected protocol's compose.override.yml to the project root.

    The override file is copied verbatim — docker compose resolves ${VAR}
    references from the .env file at runtime.
    """
    proto_dir = PROTOCOLS_DIR / config.protocol.value
    source = proto_dir / "compose.override.yml"

    if not source.exists():
        logger.error("compose.override.yml not found at %s", source)
        raise SystemExit(1)

    shutil.copy2(source, OVERRIDE_FILE)
    logger.info("Copied %s → %s", source, OVERRIDE_FILE)


# ---------------------------------------------------------------------------
# Docker orchestration
# ---------------------------------------------------------------------------


def _run_compose(command: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    """Run a docker compose command with stdout/stderr capture.

    Args:
        command: The compose subcommand and arguments (e.g., ['pull']).
        timeout: Maximum runtime in seconds.

    Returns the CompletedProcess. Exits on failure.
    """
    cmd = [
        "docker",
        "compose",
        "-f",
        str(PROJECT_ROOT / "docker-compose.yml"),
        "-f",
        str(OVERRIDE_FILE),
    ] + command

    logger.info("Running: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            logger.error(
                "docker compose failed (exit %d):\n%s",
                result.returncode,
                result.stderr.strip(),
            )
            raise SystemExit(result.returncode)
        if result.stdout.strip():
            logger.debug(result.stdout.strip())
        return result
    except subprocess.TimeoutExpired:
        logger.error("docker compose timed out after %ds.", timeout)
        raise SystemExit(1)
    except FileNotFoundError:
        logger.error("Docker not found. Ensure Docker Engine and the compose plugin are installed.")
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# Post-deploy verification
# ---------------------------------------------------------------------------


def verify_image(config: DeployConfig) -> bool:
    """Post-deploy health check: verify the container is running and the UI is reachable.

    Returns True if healthy, False otherwise.
    """
    logger.info("--- Post-deploy verification ---")

    # Check container status
    container_name = f"vpnup-{config.protocol.value.replace('_', '-')}"
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Status}}", container_name],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        status = result.stdout.strip()
        if status != "running":
            logger.error(
                "Container '%s' status: %s (expected 'running').",
                container_name,
                status,
            )
            return False
        logger.info("Container '%s' is running.", container_name)
    except FileNotFoundError:
        logger.error("Docker not found.")
        return False

    # Check UI reachability
    ui_port = config.ui_port_value
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result_code = sock.connect_ex(("127.0.0.1", ui_port))
        sock.close()
        if result_code != 0:
            logger.warning("Web UI not reachable on port %d (connection refused).", ui_port)
            logger.warning(
                "This is normal if the container is still starting. Retry in a few seconds."
            )
            return False
        logger.info("Web UI reachable on port %d.", ui_port)
        return True
    except OSError as exc:
        logger.error("Port check failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Summary output
# ---------------------------------------------------------------------------


def _print_summary(config: DeployConfig) -> None:
    """Print deployment summary to stdout."""
    ui_port = config.ui_port_value
    proto = config.protocol.value

    typer.echo("\n" + "=" * 60)
    typer.echo("  vpnUP — Deployment Complete")
    typer.echo("=" * 60)
    typer.echo(f"  Protocol:     {proto}")
    typer.echo(f"  Host:         {config.host}")
    typer.echo(f"  Web UI:       http://{config.host}:{ui_port}")
    typer.echo(f"  Username:     {config.admin_username}")
    typer.echo(f"  Password:     {config.admin_password}")
    typer.echo("-" * 60)
    typer.echo("  📋 Next steps:")
    typer.echo(f"  1. Open http://{config.host}:{ui_port} in your browser.")
    typer.echo("  2. Log in with the credentials above.")
    typer.echo("  3. Create client configs / QR codes via the Web UI.")
    typer.echo("  4. Run 'python setup.py --verify-image' to check health.")
    typer.echo("=" * 60 + "\n")

    logger.info("Deployment summary printed. Admin password shown exactly once above.")


# ---------------------------------------------------------------------------
# Protocol-specific secret generation
# ---------------------------------------------------------------------------


def _generate_protocol_secrets(config: DeployConfig) -> None:
    """Pre-generate any secrets required by the selected protocol."""
    if config.protocol == Protocol.VLESS_REALITY:
        if not config.reality_private_key:
            typer.echo("\n  🔑 Generating Reality x25519 key pair ...")
            priv, pub = generate_reality_keys()
            config.reality_private_key = priv
            config.reality_public_key = pub
            logger.info("Reality key pair generated.")
        if not config.reality_short_id:
            config.reality_short_id = generate_hex_id()

    elif config.protocol == Protocol.HYSTERIA2:
        if not config.hysteria_obfs:
            config.hysteria_obfs = generate_password(32)

    elif config.protocol == Protocol.TUIC:
        import uuid as _uuid

        if not config.tuic_uuid:
            config.tuic_uuid = str(_uuid.uuid4())
        if not config.tuic_password:
            config.tuic_password = generate_password(32)


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="vpnup",
    help="One-command VPN server deployment with bundled Web UI management.",
    no_args_is_help=False,
)


@app.command()
def main(
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Re-run prompts even if .env already exists."),
    ] = False,
    verify_image_flag: Annotated[
        bool,
        typer.Option(
            "--verify-image",
            help="Verify container health and UI reachability post-deploy.",
        ),
    ] = False,
) -> None:
    """Deploy a personal VPN server with a bundled management Web UI.

    Interactive setup collects the public IP/domain, protocol choice, admin
    credentials, and port configuration. All secrets are generated at runtime
    and written exclusively to the .env file with restricted permissions.
    """
    _setup_logging()
    logger.info("vpnUP starting. force=%s verify=%s", force, verify_image_flag)

    # --- Post-deploy verification mode ---
    if verify_image_flag:
        if not ENV_FILE.exists():
            logger.error(".env not found. Run setup without --verify-image first.")
            raise typer.Exit(code=1)
        # Load minimal config from .env
        config = _load_config_from_env()
        ok = verify_image(config)
        raise typer.Exit(code=0 if ok else 1)

    # --- Pre-flight: Docker availability ---
    _ensure_docker_available()

    # --- Check for existing .env ---
    if ENV_FILE.exists() and not force:
        msg = (
            f"Existing .env found at {ENV_FILE}.\n"
            "  Re-run with --force to overwrite, or use --verify-image for health checks."
        )
        typer.echo(msg)
        raise typer.Exit(code=0)

    # --- Collect configuration ---
    config = DeployConfig()

    typer.echo("\n🔐 vpnUP — VPN Server Deployment\n")

    config.host = _prompt_host()
    config.protocol = _prompt_protocol()
    _prompt_credentials(config)
    _prompt_ports(config)

    # --- Additional protocol-specific prompts ---
    if config.protocol == Protocol.VLESS_REALITY:
        config.reality_dest = typer.prompt(
            "Reality fallback destination (domain:port)",
            default="www.microsoft.com:443",
            show_default=True,
        ).strip()
        config.reality_server_names = typer.prompt(
            "Reality SNI allow-list (comma-separated)",
            default="www.microsoft.com,www.google.com",
            show_default=True,
        ).strip()

    elif config.protocol == Protocol.HYSTERIA2:
        config.hysteria_cert_domain = typer.prompt(
            "Domain for ACME certificate (leave blank for self-signed)",
            default="",
            show_default=False,
        ).strip()

    elif config.protocol == Protocol.TUIC:
        config.tuic_cert_domain = typer.prompt(
            "Domain for ACME certificate (leave blank for self-signed)",
            default="",
            show_default=False,
        ).strip()

    # --- Generate secrets ---
    _generate_protocol_secrets(config)

    # --- Render outputs ---
    typer.echo("\n  ⚙️  Rendering configuration ...")
    _render_env(_build_template_context(config))
    _render_override(config)
    _render_protocol_config(config)

    # --- Deploy ---
    typer.echo("  🐳 Pulling Docker images ...")
    _run_compose(["pull"])

    typer.echo("  🚀 Starting services ...")
    _run_compose(["up", "-d"])

    # --- Verify & summarize ---
    verify_image(config)
    _print_summary(config)
    logger.info("vpnUP setup completed successfully.")


def _ensure_docker_available() -> None:
    """Check that docker and docker compose are available."""
    try:
        subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error(
            "Docker Compose v2 is required but not found. "
            "Install Docker Engine with the compose plugin and try again."
        )
        raise SystemExit(1)


def _load_config_from_env() -> DeployConfig:
    """Parse .env into a minimal DeployConfig for verification mode."""
    config = DeployConfig()
    if not ENV_FILE.exists():
        return config

    raw = ENV_FILE.read_text(encoding="utf-8")
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key == "VPN_HOST":
            config.host = value
        elif key == "VPN_PROTOCOL":
            try:
                config.protocol = Protocol(value)
            except ValueError:
                pass
        elif key == "ADMIN_USERNAME":
            config.admin_username = value
        elif key == "ADMIN_PASSWORD":
            config.admin_password = value
        elif key == "WG_UI_PORT":
            config.wg_ui_port = int(value) if value.isdigit() else config.wg_ui_port
        elif key == "XUI_PORT":
            config.xui_port = int(value) if value.isdigit() else config.xui_port
        elif key == "HYSTERIA_UI_PORT":
            config.hysteria_ui_port = int(value) if value.isdigit() else config.hysteria_ui_port
        elif key == "TUIC_UI_PORT":
            config.tuic_ui_port = int(value) if value.isdigit() else config.tuic_ui_port

    return config


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
