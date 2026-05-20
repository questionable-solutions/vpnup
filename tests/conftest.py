"""Shared fixtures for the vpnUP test suite."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from setup import DeployConfig, Protocol


@pytest.fixture
def temp_project_root(tmp_path: Path) -> Path:
    """Create a temporary project root with minimal structure."""
    (tmp_path / "protocols").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".env.example").write_text(
        "VPN_HOST={{VPN_HOST}}\nADMIN_PASSWORD={{ADMIN_PASSWORD}}\n"
    )
    (tmp_path / "docker-compose.yml").write_text(
        "version: '3.8'\nnetworks:\n  vpn-net:\n    driver: bridge\n"
    )
    return tmp_path


@pytest.fixture
def wireguard_proto_dir(temp_project_root: Path) -> Path:
    """Create a wireguard protocol directory with override file."""
    proto_dir = temp_project_root / "protocols" / "wireguard"
    proto_dir.mkdir(parents=True, exist_ok=True)
    (proto_dir / "compose.override.yml").write_text(
        "services:\n  wireguard:\n    image: ghcr.io/wg-easy/wg-easy:14\n"
    )
    return proto_dir


@pytest.fixture
def vless_proto_dir(temp_project_root: Path) -> Path:
    """Create a vless-reality protocol directory with override and config template."""
    proto_dir = temp_project_root / "protocols" / "vless-reality"
    proto_dir.mkdir(parents=True, exist_ok=True)
    (proto_dir / "compose.override.yml").write_text(
        "services:\n  vless-reality:\n    image: ghcr.io/azumi67/3x-ui:latest\n"
    )
    (proto_dir / "config.template").write_text(
        '{"port": "{{VLESS_PORT}}", "key": "{{REALITY_PRIVATE_KEY}}"}'
    )
    return proto_dir


@pytest.fixture
def base_config() -> DeployConfig:
    """Return a DeployConfig with sensible test defaults."""
    return DeployConfig(
        host="203.0.113.1",
        protocol=Protocol.WIREGUARD,
        admin_username="admin",
        admin_password="test-password-123",
        wg_port=51820,
        wg_ui_port=51821,
    )


@pytest.fixture
def vless_config() -> DeployConfig:
    """Return a DeployConfig for VLESS + Reality."""
    return DeployConfig(
        host="vpn.example.com",
        protocol=Protocol.VLESS_REALITY,
        admin_username="admin",
        admin_password="secure-pass-456",
        vless_port=8443,
        xui_port=2053,
        reality_private_key="aGVsbG8gd29ybGQgdGhpcyBpcyBhIHRlc3Qga2V5",
        reality_public_key="cHVibGljIGtleSB0ZXN0IHZhbHVlIGZvciB1bml0IHRlc3Rz",
        reality_short_id="abcdef12",
    )


@pytest.fixture
def mock_subprocess_run():
    """Mock subprocess.run to avoid real Docker calls."""
    with patch("subprocess.run") as mock_run:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "running\n"
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        yield mock_run


@pytest.fixture
def mock_docker_available(mock_subprocess_run):
    """Mock docker compose version check as successful."""
    mock_subprocess_run.return_value.returncode = 0
    return mock_subprocess_run
