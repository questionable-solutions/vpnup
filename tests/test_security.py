"""Tests for security helpers: password/key generation, umask, secret handling."""

from __future__ import annotations

import os
import re
import stat
from unittest.mock import MagicMock, patch

import pytest

from setup import (
    DeployConfig,
    Protocol,
    _generate_protocol_secrets,
    _secure_umask,
    generate_hex_id,
    generate_password,
    generate_reality_keys,
)


class TestGeneratePassword:
    """Cryptographic password generation."""

    def test_default_length(self) -> None:
        pw = generate_password()
        assert len(pw) == 24

    def test_custom_length(self) -> None:
        pw = generate_password(16)
        assert len(pw) == 16

    def test_no_whitespace(self) -> None:
        for _ in range(10):
            pw = generate_password()
            assert " " not in pw
            assert "\t" not in pw
            assert "\n" not in pw

    def test_no_shell_specials(self) -> None:
        """Password must not contain characters that break shell strings."""
        for _ in range(10):
            pw = generate_password()
            assert "\\" not in pw
            assert "`" not in pw
            assert "$" not in pw
            assert "'" not in pw
            assert '"' not in pw

    def test_randomness(self) -> None:
        """Two consecutive calls should produce different passwords."""
        pw1 = generate_password()
        pw2 = generate_password()
        assert pw1 != pw2

    def test_character_variety(self) -> None:
        """Password should contain multiple character types."""
        pw = generate_password(100)
        has_upper = any(c.isupper() for c in pw)
        has_lower = any(c.islower() for c in pw)
        has_digit = any(c.isdigit() for c in pw)
        has_special = any(not c.isalnum() for c in pw)
        assert has_upper and has_lower and has_digit and has_special


class TestGenerateHexId:
    """Hex ID generation for Reality shortId."""

    def test_default_length(self) -> None:
        hid = generate_hex_id()
        assert len(hid) == 8

    def test_hex_characters(self) -> None:
        hid = generate_hex_id(16)
        assert all(c in "0123456789abcdef" for c in hid)

    def test_randomness(self) -> None:
        assert generate_hex_id() != generate_hex_id()


class TestGenerateRealityKeys:
    """x25519 key pair generation via openssl."""

    def test_generates_keys_successfully(self) -> None:
        # Simulate openssl output
        priv_pem = "-----BEGIN PRIVATE KEY-----\nabc123\n-----END PRIVATE KEY-----"
        pub_pem = "-----BEGIN PUBLIC KEY-----\ndef456\n-----END PUBLIC KEY-----"

        with patch("subprocess.run") as mock_run:
            mock_priv = MagicMock()
            mock_priv.stdout = priv_pem
            mock_pub = MagicMock()
            mock_pub.stdout = pub_pem
            mock_run.side_effect = [mock_priv, mock_pub]

            priv, pub = generate_reality_keys()

            assert priv == "abc123"
            assert pub == "def456"
            assert mock_run.call_count == 2

    def test_strips_all_headers(self) -> None:
        priv_pem = "-----BEGIN PRIVATE KEY-----\nkeydata\n-----END PRIVATE KEY-----\n"
        pub_pem = "-----BEGIN PUBLIC KEY-----\npubdata\n-----END PUBLIC KEY-----\n"

        with patch("subprocess.run") as mock_run:
            mock_priv = MagicMock()
            mock_priv.stdout = priv_pem
            mock_pub = MagicMock()
            mock_pub.stdout = pub_pem
            mock_run.side_effect = [mock_priv, mock_pub]

            priv, pub = generate_reality_keys()
            assert priv == "keydata"
            assert pub == "pubdata"

    def test_exits_on_openssl_failure(self) -> None:
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(SystemExit):
                generate_reality_keys()


class TestSecureUmask:
    """File permission security."""

    def test_sets_restrictive_umask(self) -> None:
        old = os.umask(0o022)
        try:
            _secure_umask()
            # After _secure_umask, new umask should be 077
            # Verify by checking what new files get
            new = os.umask(0o022)
            assert new == 0o077, f"Expected 0o077, got {oct(new)}"
        finally:
            os.umask(old)


class TestGenerateProtocolSecrets:
    """Per-protocol secret generation logic."""

    def test_vless_generates_keys_when_empty(self) -> None:
        config = DeployConfig(
            host="10.0.0.1",
            protocol=Protocol.VLESS_REALITY,
        )
        assert config.reality_private_key == ""
        assert config.reality_short_id == ""

        with patch("setup.generate_reality_keys", return_value=("priv", "pub")):
            with patch("setup.generate_hex_id", return_value="abcd1234"):
                _generate_protocol_secrets(config)

        assert config.reality_private_key == "priv"
        assert config.reality_public_key == "pub"
        assert config.reality_short_id == "abcd1234"

    def test_vless_preserves_existing_keys(self) -> None:
        config = DeployConfig(
            host="10.0.0.1",
            protocol=Protocol.VLESS_REALITY,
            reality_private_key="existing-priv",
            reality_short_id="existing123",
        )

        with patch("setup.generate_reality_keys") as mock_gen:
            _generate_protocol_secrets(config)
            mock_gen.assert_not_called()

        assert config.reality_private_key == "existing-priv"

    def test_hysteria2_generates_obfs_when_empty(self) -> None:
        config = DeployConfig(
            host="10.0.0.1",
            protocol=Protocol.HYSTERIA2,
        )
        assert config.hysteria_obfs == ""

        _generate_protocol_secrets(config)
        assert len(config.hysteria_obfs) == 32

    def test_tuic_generates_uuid_and_password(self) -> None:
        config = DeployConfig(
            host="10.0.0.1",
            protocol=Protocol.TUIC,
        )
        assert config.tuic_uuid == ""
        assert config.tuic_password == ""

        _generate_protocol_secrets(config)

        assert len(config.tuic_uuid) == 36  # Standard UUID length
        assert len(config.tuic_password) == 32

    def test_wireguard_no_secrets_generated(self) -> None:
        config = DeployConfig(
            host="10.0.0.1",
            protocol=Protocol.WIREGUARD,
        )
        before = config.admin_password
        _generate_protocol_secrets(config)
        # WireGuard has no auto-generated secrets besides admin password
        assert config.admin_password == before
