"""Tests for .env rendering and template context building."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from setup import (
    ENV_EXAMPLE,
    ENV_FILE,
    DeployConfig,
    Protocol,
    _build_template_context,
    _render_env,
)


class TestBuildTemplateContext:
    """Template context generation for .env rendering."""

    def test_wireguard_context_has_all_keys(self, base_config: DeployConfig) -> None:
        ctx = _build_template_context(base_config)
        assert ctx["VPN_HOST"] == "203.0.113.1"
        assert ctx["VPN_PROTOCOL"] == "wireguard"
        assert ctx["ADMIN_PASSWORD"] == "test-password-123"
        assert ctx["WG_PORT"] == "51820"
        assert ctx["WG_UI_PORT"] == "51821"

    def test_vless_context_includes_reality_keys(
        self, vless_config: DeployConfig
    ) -> None:
        ctx = _build_template_context(vless_config)
        assert ctx["VLESS_PORT"] == "8443"
        assert ctx["XUI_PORT"] == "2053"
        assert ctx["REALITY_PRIVATE_KEY"] == vless_config.reality_private_key
        assert ctx["REALITY_SHORT_ID"] == "abcdef12"

    def test_context_always_returns_strings(self, base_config: DeployConfig) -> None:
        ctx = _build_template_context(base_config)
        for key, value in ctx.items():
            assert isinstance(value, str), (
                f"Key '{key}' has non-str value: {type(value)}"
            )

    def test_empty_secrets_rendered_as_empty_string(
        self, base_config: DeployConfig
    ) -> None:
        base_config.admin_password = ""
        ctx = _build_template_context(base_config)
        assert ctx["ADMIN_PASSWORD"] == ""


class TestRenderEnv:
    """.env file rendering from .env.example template."""

    ENV_TEMPLATE = (
        "# vpnUP env\n"
        "VPN_HOST={{VPN_HOST}}\n"
        "VPN_PROTOCOL={{VPN_PROTOCOL}}\n"
        "ADMIN_PASSWORD={{ADMIN_PASSWORD}}\n"
        "WG_PORT={{WG_PORT}}\n"
        "# comment line\n"
        "WG_DEFAULT_DNS={{WG_DEFAULT_DNS}}\n"
    )

    def test_basic_rendering(self, tmp_path: Path, base_config: DeployConfig) -> None:
        template = tmp_path / ".env.example"
        template.write_text(self.ENV_TEMPLATE)
        output = tmp_path / ".env"

        _render_env(
            _build_template_context(base_config),
            template_path=template,
            output_path=output,
        )

        rendered = output.read_text()
        assert "VPN_HOST=203.0.113.1" in rendered
        assert "VPN_PROTOCOL=wireguard" in rendered
        assert "ADMIN_PASSWORD=test-password-123" in rendered
        assert "WG_PORT=51820" in rendered

    def test_comments_preserved(
        self, tmp_path: Path, base_config: DeployConfig
    ) -> None:
        template = tmp_path / ".env.example"
        template.write_text(self.ENV_TEMPLATE)
        output = tmp_path / ".env"

        _render_env(
            _build_template_context(base_config),
            template_path=template,
            output_path=output,
        )

        rendered = output.read_text()
        assert "# vpnUP env" in rendered
        assert "# comment line" in rendered

    def test_unknown_placeholder_preserved(
        self, tmp_path: Path, base_config: DeployConfig
    ) -> None:
        template = tmp_path / ".env.example"
        template.write_text("UNKNOWN={{NO_SUCH_VAR}}\nVPN_HOST={{VPN_HOST}}\n")
        output = tmp_path / ".env"

        _render_env(
            _build_template_context(base_config),
            template_path=template,
            output_path=output,
        )

        rendered = output.read_text()
        assert "{{NO_SUCH_VAR}}" in rendered
        assert "VPN_HOST=203.0.113.1" in rendered

    def test_file_permissions_restricted(
        self, tmp_path: Path, base_config: DeployConfig
    ) -> None:
        template = tmp_path / ".env.example"
        template.write_text("VPN_HOST={{VPN_HOST}}\n")
        output = tmp_path / ".env"

        _render_env(
            _build_template_context(base_config),
            template_path=template,
            output_path=output,
        )

        # Check that the file is owner-readable only (umask 077)
        stat = output.stat()
        assert stat.st_mode & 0o077 == 0, (
            f"Output file has group/other permissions: {oct(stat.st_mode)}"
        )

    def test_missing_template_exits(
        self, tmp_path: Path, base_config: DeployConfig
    ) -> None:
        with pytest.raises(SystemExit):
            _render_env(
                {},
                template_path=tmp_path / "nonexistent",
                output_path=tmp_path / ".env",
            )

    def test_multiple_replacements_per_line(self, tmp_path: Path) -> None:
        config = DeployConfig(
            host="10.0.0.1",
            protocol=Protocol.WIREGUARD,
            wg_port=9999,
            wg_ui_port=8888,
        )
        template = tmp_path / ".env.example"
        template.write_text("WG_PORT={{WG_PORT}}  WG_UI_PORT={{WG_UI_PORT}}\n")
        output = tmp_path / ".env"

        _render_env(
            _build_template_context(config),
            template_path=template,
            output_path=output,
        )

        rendered = output.read_text()
        assert "WG_PORT=9999" in rendered
        assert "WG_UI_PORT=8888" in rendered
