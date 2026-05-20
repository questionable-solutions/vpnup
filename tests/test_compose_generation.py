"""Tests for compose override generation and protocol config rendering."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from setup import (
    OVERRIDE_FILE,
    PROJECT_ROOT,
    PROTOCOLS_DIR,
    DeployConfig,
    Protocol,
    _render_override,
    _render_protocol_config,
)


class TestRenderOverride:
    """Compose override file selection and copying."""

    def test_copies_wireguard_override(
        self, tmp_path: Path, wireguard_proto_dir: Path, base_config: DeployConfig
    ) -> None:
        with patch("setup.PROTOCOLS_DIR", wireguard_proto_dir.parent):
            with patch("setup.OVERRIDE_FILE", tmp_path / "docker-compose.override.yml"):
                _render_override(base_config)

        override = tmp_path / "docker-compose.override.yml"
        assert override.exists()
        content = override.read_text()
        assert "ghcr.io/wg-easy/wg-easy:14" in content

    def test_copies_vless_override(
        self, tmp_path: Path, vless_proto_dir: Path, vless_config: DeployConfig
    ) -> None:
        with patch("setup.PROTOCOLS_DIR", vless_proto_dir.parent):
            with patch("setup.OVERRIDE_FILE", tmp_path / "docker-compose.override.yml"):
                _render_override(vless_config)

        override = tmp_path / "docker-compose.override.yml"
        assert override.exists()
        content = override.read_text()
        assert "ghcr.io/azumi67/3x-ui:latest" in content

    def test_missing_override_exits(self, tmp_path: Path, base_config: DeployConfig) -> None:
        proto_dir = tmp_path / "protocols" / base_config.protocol.value
        proto_dir.mkdir(parents=True)
        # Don't create compose.override.yml

        with patch("setup.PROTOCOLS_DIR", proto_dir.parent):
            with patch("setup.OVERRIDE_FILE", tmp_path / "override.yml"):
                with pytest.raises(SystemExit):
                    _render_override(base_config)

    def test_override_overwrites_existing(
        self, tmp_path: Path, wireguard_proto_dir: Path, base_config: DeployConfig
    ) -> None:
        target = tmp_path / "docker-compose.override.yml"
        target.write_text("old content")

        with patch("setup.PROTOCOLS_DIR", wireguard_proto_dir.parent):
            with patch("setup.OVERRIDE_FILE", target):
                _render_override(base_config)

        assert "old content" not in target.read_text()
        assert "ghcr.io/wg-easy/wg-easy:14" in target.read_text()


class TestRenderProtocolConfig:
    """Protocol-specific config.template rendering."""

    def test_renders_vless_config_template(
        self, tmp_path: Path, vless_proto_dir: Path, vless_config: DeployConfig
    ) -> None:
        output_dir = tmp_path / "vless-reality-data"

        with patch("setup.PROTOCOLS_DIR", vless_proto_dir.parent):
            with patch("setup.PROJECT_ROOT", tmp_path):
                _render_protocol_config(vless_config)

        config_file = output_dir / "config.json"
        assert config_file.exists()
        content = config_file.read_text()
        assert str(vless_config.vless_port) in content or '"{{VLESS_PORT}}"' not in content

    def test_skips_when_no_template(self, tmp_path: Path, base_config: DeployConfig) -> None:
        # WireGuard has no config.template in PROTOCOLS_WITH_TEMPLATES
        proto_dir = tmp_path / "protocols" / "wireguard"
        proto_dir.mkdir(parents=True)

        with patch("setup.PROTOCOLS_DIR", proto_dir.parent):
            with patch("setup.PROJECT_ROOT", tmp_path):
                # Should not raise, just skip
                _render_protocol_config(base_config)

        # No wireguard-data/config.json should be created
        assert not (tmp_path / "wireguard-data" / "config.json").exists()

    def test_warns_when_template_missing(self, tmp_path: Path, caplog) -> None:
        """When a protocol IS in PROTOCOLS_WITH_TEMPLATES but the file is missing."""
        config = DeployConfig(
            host="10.0.0.1",
            protocol=Protocol.VLESS_REALITY,
        )
        proto_dir = tmp_path / "protocols" / "vless-reality"
        proto_dir.mkdir(parents=True)
        # No config.template created

        import logging

        caplog.set_level(logging.WARNING)

        with patch("setup.PROTOCOLS_DIR", proto_dir.parent):
            with patch("setup.PROJECT_ROOT", tmp_path):
                _render_protocol_config(config)

        assert any("not found" in r.message.lower() for r in caplog.records)


class TestDeployConfigUiPort:
    """UI port resolution via DeployConfig properties."""

    def test_wireguard_ui_port(self, base_config: DeployConfig) -> None:
        assert base_config.ui_port_value == 51821
        assert base_config.ui_port_attr == "wg_ui_port"

    def test_vless_ui_port(self, vless_config: DeployConfig) -> None:
        assert vless_config.ui_port_value == 2053
        assert vless_config.ui_port_attr == "xui_port"

    def test_hysteria_ui_port(self) -> None:
        config = DeployConfig(
            host="10.0.0.1",
            protocol=Protocol.HYSTERIA2,
            hysteria_ui_port=9090,
        )
        assert config.ui_port_value == 9090

    def test_tuic_ui_port(self) -> None:
        config = DeployConfig(
            host="10.0.0.1",
            protocol=Protocol.TUIC,
            tuic_ui_port=7070,
        )
        assert config.ui_port_value == 7070
