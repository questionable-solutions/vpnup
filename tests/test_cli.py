"""Tests for CLI entrypoint, config loading, and docker orchestration stubs."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from setup import (
    ENV_EXAMPLE,
    ENV_FILE,
    OVERRIDE_FILE,
    PROTOCOLS_DIR,
    DeployConfig,
    Protocol,
    _ensure_docker_available,
    _load_config_from_env,
    _print_summary,
    _run_compose,
    app,
    verify_image,
)

# ---------------------------------------------------------------------------
# CLI Runner fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def isolated_project(tmp_path: Path, monkeypatch) -> Path:
    """Set up an isolated project root with all required files."""
    # Create protocol dirs
    for proto in ["wireguard", "vless-reality", "hysteria2", "tuic"]:
        pdir = tmp_path / "protocols" / proto
        pdir.mkdir(parents=True)
        (pdir / "compose.override.yml").write_text(
            f"services:\n  {proto}:\n    image: test/{proto}:latest\n"
        )
    # config.template for vless-reality
    (tmp_path / "protocols" / "vless-reality" / "config.template").write_text(
        '{"port": "{{VLESS_PORT}}"}'
    )
    # .env.example
    (tmp_path / ".env.example").write_text(
        "VPN_HOST={{VPN_HOST}}\n"
        "VPN_PROTOCOL={{VPN_PROTOCOL}}\n"
        "ADMIN_USERNAME={{ADMIN_USERNAME}}\n"
        "ADMIN_PASSWORD={{ADMIN_PASSWORD}}\n"
        "WG_PORT={{WG_PORT}}\n"
        "WG_UI_PORT={{WG_UI_PORT}}\n"
        "WG_DEFAULT_DNS={{WG_DEFAULT_DNS}}\n"
        "WG_ALLOWED_IPS={{WG_ALLOWED_IPS}}\n"
        "WG_MTU={{WG_MTU}}\n"
        "XUI_PORT={{XUI_PORT}}\n"
        "VLESS_PORT={{VLESS_PORT}}\n"
        "REALITY_DEST={{REALITY_DEST}}\n"
        "REALITY_SERVER_NAMES={{REALITY_SERVER_NAMES}}\n"
        "REALITY_PRIVATE_KEY={{REALITY_PRIVATE_KEY}}\n"
        "REALITY_PUBLIC_KEY={{REALITY_PUBLIC_KEY}}\n"
        "REALITY_SHORT_ID={{REALITY_SHORT_ID}}\n"
        "HYSTERIA_PORT={{HYSTERIA_PORT}}\n"
        "HYSTERIA_UI_PORT={{HYSTERIA_UI_PORT}}\n"
        "HYSTERIA_OBFS={{HYSTERIA_OBFS}}\n"
        "HYSTERIA_CERT_DOMAIN={{HYSTERIA_CERT_DOMAIN}}\n"
        "TUIC_PORT={{TUIC_PORT}}\n"
        "TUIC_UI_PORT={{TUIC_UI_PORT}}\n"
        "TUIC_CERT_DOMAIN={{TUIC_CERT_DOMAIN}}\n"
        "TUIC_UUID={{TUIC_UUID}}\n"
        "TUIC_PASSWORD={{TUIC_PASSWORD}}\n"
    )
    # docker-compose.yml
    (tmp_path / "docker-compose.yml").write_text(
        "version: '3.8'\nnetworks:\n  vpn-net:\n    driver: bridge\n"
    )

    # Patch constants
    monkeypatch.setattr("setup.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("setup.PROTOCOLS_DIR", tmp_path / "protocols")
    monkeypatch.setattr("setup.ENV_EXAMPLE", tmp_path / ".env.example")
    monkeypatch.setattr("setup.ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr("setup.OVERRIDE_FILE", tmp_path / "docker-compose.override.yml")
    monkeypatch.setattr("setup.LOG_FILE", tmp_path / "setup.log")

    return tmp_path


# ---------------------------------------------------------------------------
# _load_config_from_env
# ---------------------------------------------------------------------------


class TestLoadConfigFromEnv:
    def test_parses_wireguard_config(self, tmp_path: Path, monkeypatch) -> None:
        env_content = (
            "VPN_HOST=203.0.113.1\n"
            "VPN_PROTOCOL=wireguard\n"
            "ADMIN_USERNAME=admin\n"
            "ADMIN_PASSWORD=secret123\n"
            "WG_UI_PORT=51821\n"
        )
        env_file = tmp_path / ".env"
        env_file.write_text(env_content)
        monkeypatch.setattr("setup.ENV_FILE", env_file)

        config = _load_config_from_env()
        assert config.host == "203.0.113.1"
        assert config.protocol == Protocol.WIREGUARD
        assert config.admin_username == "admin"
        assert config.admin_password == "secret123"
        assert config.wg_ui_port == 51821

    def test_parses_vless_config(self, tmp_path: Path, monkeypatch) -> None:
        env_content = (
            "VPN_HOST=vpn.example.com\n"
            "VPN_PROTOCOL=vless-reality\n"
            "ADMIN_USERNAME=myadmin\n"
            "ADMIN_PASSWORD=mypass\n"
            "XUI_PORT=2053\n"
        )
        env_file = tmp_path / ".env"
        env_file.write_text(env_content)
        monkeypatch.setattr("setup.ENV_FILE", env_file)

        config = _load_config_from_env()
        assert config.host == "vpn.example.com"
        assert config.protocol == Protocol.VLESS_REALITY
        assert config.xui_port == 2053

    def test_handles_quoted_values(self, tmp_path: Path, monkeypatch) -> None:
        env_content = "VPN_HOST=\"203.0.113.1\"\nADMIN_PASSWORD='secret'\n"
        env_file = tmp_path / ".env"
        env_file.write_text(env_content)
        monkeypatch.setattr("setup.ENV_FILE", env_file)

        config = _load_config_from_env()
        assert config.host == "203.0.113.1"
        assert config.admin_password == "secret"

    def test_ignores_comments_and_blanks(self, tmp_path: Path, monkeypatch) -> None:
        env_content = (
            "# This is a comment\n\nVPN_HOST=10.0.0.1\n# Another comment\nVPN_PROTOCOL=wireguard\n"
        )
        env_file = tmp_path / ".env"
        env_file.write_text(env_content)
        monkeypatch.setattr("setup.ENV_FILE", env_file)

        config = _load_config_from_env()
        assert config.host == "10.0.0.1"

    def test_returns_defaults_when_no_env(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr("setup.ENV_FILE", tmp_path / "nonexistent")
        config = _load_config_from_env()
        assert config.host == ""
        assert config.protocol == Protocol.WIREGUARD


# ---------------------------------------------------------------------------
# Docker helpers
# ---------------------------------------------------------------------------


class TestEnsureDockerAvailable:
    def test_docker_available(self) -> None:
        with patch("subprocess.run") as mock_run:
            _ensure_docker_available()
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "docker" in args

    def test_docker_not_found(self) -> None:
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(SystemExit):
                _ensure_docker_available()

    def test_docker_compose_fails(self) -> None:
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "cmd")):
            with pytest.raises(SystemExit):
                _ensure_docker_available()


class TestRunCompose:
    def test_successful_compose(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr("setup.OVERRIDE_FILE", tmp_path / "override.yml")
        (tmp_path / "docker-compose.yml").write_text("version: '3.8'\n")
        (tmp_path / "override.yml").write_text("services:\n  test:\n    image: test\n")
        monkeypatch.setattr("setup.PROJECT_ROOT", tmp_path)

        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "done"
            mock_result.stderr = ""
            mock_run.return_value = mock_result

            _run_compose(["up", "-d"])

    def test_compose_failure_exits(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr("setup.OVERRIDE_FILE", tmp_path / "override.yml")
        (tmp_path / "docker-compose.yml").write_text("version: '3.8'\n")
        (tmp_path / "override.yml").write_text("services:\n  test:\n    image: test\n")
        monkeypatch.setattr("setup.PROJECT_ROOT", tmp_path)

        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stderr = "error occurred"
            mock_run.return_value = mock_result

            with pytest.raises(SystemExit):
                _run_compose(["up", "-d"])

    def test_compose_timeout(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr("setup.OVERRIDE_FILE", tmp_path / "override.yml")
        (tmp_path / "docker-compose.yml").write_text("version: '3.8'\n")
        (tmp_path / "override.yml").write_text("services:\n  test:\n    image: test\n")
        monkeypatch.setattr("setup.PROJECT_ROOT", tmp_path)

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 1)):
            with pytest.raises(SystemExit):
                _run_compose(["pull"], timeout=1)


class TestVerifyImage:
    def test_container_running_and_ui_reachable(self) -> None:
        config = DeployConfig(
            host="10.0.0.1",
            protocol=Protocol.WIREGUARD,
            wg_ui_port=51821,
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = "running\n"
            with patch("socket.socket") as mock_socket:
                mock_sock_instance = MagicMock()
                mock_sock_instance.connect_ex.return_value = 0
                mock_socket.return_value = mock_sock_instance

                result = verify_image(config)
                assert result is True

    def test_container_not_running(self) -> None:
        config = DeployConfig(host="10.0.0.1", protocol=Protocol.WIREGUARD)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = "stopped\n"
            result = verify_image(config)
            assert result is False

    def test_ui_not_reachable(self) -> None:
        config = DeployConfig(
            host="10.0.0.1",
            protocol=Protocol.WIREGUARD,
            wg_ui_port=51821,
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = "running\n"
            with patch("socket.socket") as mock_socket:
                mock_sock_instance = MagicMock()
                mock_sock_instance.connect_ex.return_value = 1  # Connection refused
                mock_socket.return_value = mock_sock_instance

                result = verify_image(config)
                assert result is False

    def test_docker_not_found(self) -> None:
        config = DeployConfig(host="10.0.0.1", protocol=Protocol.WIREGUARD)

        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = verify_image(config)
            assert result is False


# ---------------------------------------------------------------------------
# Print summary
# ---------------------------------------------------------------------------


class TestPrintSummary:
    def test_prints_wireguard_summary(self) -> None:
        config = DeployConfig(
            host="203.0.113.1",
            protocol=Protocol.WIREGUARD,
            admin_username="admin",
            admin_password="test123",
            wg_ui_port=51821,
        )

        with patch("typer.echo") as mock_echo:
            _print_summary(config)
            # Verify key information is in the output
            calls = [str(c) for c in mock_echo.call_args_list]
            combined = " ".join(calls)
            assert "203.0.113.1" in combined
            assert "51821" in combined
            assert "admin" in combined
            assert "test123" in combined
            assert "wireguard" in combined

    def test_prints_vless_summary(self) -> None:
        config = DeployConfig(
            host="vpn.example.com",
            protocol=Protocol.VLESS_REALITY,
            admin_username="root",
            admin_password="pass456",
            xui_port=2053,
        )

        with patch("typer.echo") as mock_echo:
            _print_summary(config)
            calls = [str(c) for c in mock_echo.call_args_list]
            combined = " ".join(calls)
            assert "vpn.example.com" in combined
            assert "2053" in combined
            assert "vless-reality" in combined


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


class TestCliVerifyImage:
    """Test the --verify-image CLI flag."""

    def test_verify_without_env_fails(self, isolated_project: Path, runner: CliRunner) -> None:
        result = runner.invoke(app, ["--verify-image"])
        assert result.exit_code == 1

    def test_verify_with_env_succeeds(self, isolated_project: Path, runner: CliRunner) -> None:
        # Write .env first
        (isolated_project / ".env").write_text(
            "VPN_HOST=10.0.0.1\nVPN_PROTOCOL=wireguard\nWG_UI_PORT=51821\n"
        )

        with patch("setup.verify_image", return_value=True):
            result = runner.invoke(app, ["--verify-image"])
            assert result.exit_code == 0

    def test_verify_with_env_fails_when_unhealthy(
        self, isolated_project: Path, runner: CliRunner
    ) -> None:
        (isolated_project / ".env").write_text(
            "VPN_HOST=10.0.0.1\nVPN_PROTOCOL=wireguard\nWG_UI_PORT=51821\n"
        )

        with patch("setup.verify_image", return_value=False):
            result = runner.invoke(app, ["--verify-image"])
            assert result.exit_code == 1


class TestCliExistingEnv:
    """Test behavior when .env already exists."""

    def test_existing_env_skips_prompts(self, isolated_project: Path, runner: CliRunner) -> None:
        (isolated_project / ".env").write_text("VPN_HOST=10.0.0.1\n")

        with patch("setup._ensure_docker_available"):
            result = runner.invoke(app, [])
            assert result.exit_code == 0
            assert "Existing .env found" in result.output

    def test_force_overwrites_env(self, isolated_project: Path, runner: CliRunner) -> None:
        (isolated_project / ".env").write_text("VPN_HOST=10.0.0.1\n")

        # With --force, it should proceed to prompts. We need to provide input.
        with patch("setup._ensure_docker_available"):
            result = runner.invoke(app, ["--force"], input="\n")
            # It will fail at interactive prompts (no TTY), but should NOT
            # print the "Existing .env" message
            assert "Existing .env found" not in result.output


class TestCliFullFlow:
    """Test the full interactive deployment flow (mocked docker)."""

    def test_full_wireguard_deploy(self, isolated_project: Path, runner: CliRunner) -> None:
        """Simulate a complete WireGuard deployment."""
        user_input = (
            "203.0.113.1\n"  # host
            "1\n"  # protocol (wireguard)
            "\n"  # username (default: admin)
            "n\n"  # custom password? no
            "\n"  # WG port (default: 51820)
            "\n"  # UI port (default: 51821)
        )

        with patch("setup._ensure_docker_available"):
            with patch("setup._run_compose") as mock_compose:
                with patch("setup.verify_image", return_value=True):
                    with patch("setup._print_summary"):
                        result = runner.invoke(app, ["--force"], input=user_input)

        assert result.exit_code == 0
        # .env should be created
        env_file = isolated_project / ".env"
        assert env_file.exists()
        content = env_file.read_text()
        assert "VPN_HOST=203.0.113.1" in content
        assert "VPN_PROTOCOL=wireguard" in content
        assert "ADMIN_USERNAME=admin" in content
        # Docker compose should have been called
        assert mock_compose.call_count >= 2  # pull + up

    def test_full_vless_deploy(self, isolated_project: Path, runner: CliRunner) -> None:
        """Simulate a complete VLESS+Reality deployment."""
        user_input = (
            "vpn.example.com\n"  # host
            "2\n"  # protocol (vless-reality)
            "myadmin\n"  # username
            "y\n"  # custom password? yes
            "mypassword123\n"  # password
            "mypassword123\n"  # confirm
            "8443\n"  # VLESS port (avoid privileged 443)
            "2083\n"  # XUI port
            "\n"  # reality dest (default)
            "\n"  # SNI allow-list (default)
        )

        with patch("setup._ensure_docker_available"):
            with patch("setup.generate_reality_keys", return_value=("priv", "pub")):
                with patch("setup.generate_hex_id", return_value="abcd1234"):
                    with patch("setup._run_compose"):
                        with patch("setup.verify_image", return_value=True):
                            with patch("setup._print_summary"):
                                result = runner.invoke(app, ["--force"], input=user_input)

        assert result.exit_code == 0, f"STDERR: {result.stderr}\nSTDOUT: {result.output[:500]}"
        env_file = isolated_project / ".env"
        assert env_file.exists()
        content = env_file.read_text()
        assert "VPN_HOST=vpn.example.com" in content
        assert "VPN_PROTOCOL=vless-reality" in content
        assert "ADMIN_USERNAME=myadmin" in content
        assert "ADMIN_PASSWORD=mypassword123" in content
        assert "VLESS_PORT=8443" in content
        assert "XUI_PORT=2083" in content
        assert "REALITY_PRIVATE_KEY=priv" in content
        assert "REALITY_SHORT_ID=abcd1234" in content

    def test_invalid_host_rejected(self, isolated_project: Path, runner: CliRunner) -> None:
        """Invalid host input should result in an error."""
        user_input = (
            "not-a-valid!!!\n"  # invalid host
            "203.0.113.1\n"  # valid host (second attempt)
            "1\n"  # wireguard
            "\n"  # username
            "n\n"  # no custom password
            "\n"  # WG port
            "\n"  # UI port
        )

        with patch("setup._ensure_docker_available"):
            with patch("setup._run_compose"):
                with patch("setup.verify_image", return_value=True):
                    with patch("setup._print_summary"):
                        result = runner.invoke(app, ["--force"], input=user_input)

        assert result.exit_code == 0

    def test_mismatched_passwords_rejected(self, isolated_project: Path, runner: CliRunner) -> None:
        """Password mismatch should force re-prompt."""
        user_input = (
            "10.0.0.1\n"  # host
            "1\n"  # wireguard
            "admin\n"  # username
            "y\n"  # custom password? yes
            "firstpass\n"  # first password
            "secondpass\n"  # mismatch
            "goodpass\n"  # retry
            "goodpass\n"  # confirm
            "\n"  # WG port
            "\n"  # UI port
        )

        with patch("setup._ensure_docker_available"):
            with patch("setup._run_compose"):
                with patch("setup.verify_image", return_value=True):
                    with patch("setup._print_summary"):
                        result = runner.invoke(app, ["--force"], input=user_input)

        assert result.exit_code == 0
        content = (isolated_project / ".env").read_text()
        assert "ADMIN_PASSWORD=goodpass" in content

    def test_experimental_protocol_warns(self, isolated_project: Path, runner: CliRunner) -> None:
        """Selecting hysteria2 should show experimental warning."""
        user_input = (
            "10.0.0.1\n"  # host
            "3\n"  # hysteria2 (experimental)
            "y\n"  # continue anyway? yes
            "admin\n"  # username
            "n\n"  # no custom password
            "\n"  # hysteria port
            "\n"  # UI port
            "\n"  # cert domain (blank)
        )

        with patch("setup._ensure_docker_available"):
            with patch("setup._run_compose"):
                with patch("setup.verify_image", return_value=True):
                    with patch("setup._print_summary"):
                        result = runner.invoke(app, ["--force"], input=user_input)

        assert result.exit_code == 0
        assert "EXPERIMENTAL" in result.output
