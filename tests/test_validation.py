"""Tests for input validation functions."""

from __future__ import annotations

import pytest

from setup import (
    ValidationError,
    check_port_available,
    validate_host,
    validate_port,
    validate_protocol,
)


class TestValidateHost:
    """IP address and domain name validation."""

    def test_valid_public_ipv4(self) -> None:
        assert validate_host("203.0.113.1") == "203.0.113.1"

    def test_valid_public_ipv6(self) -> None:
        assert validate_host("2001:db8::1") == "2001:db8::1"

    def test_valid_domain(self) -> None:
        assert validate_host("vpn.example.com") == "vpn.example.com"

    def test_valid_subdomain(self) -> None:
        assert validate_host("my.vpn.example.co.uk") == "my.vpn.example.co.uk"

    def test_rejects_loopback_ipv4(self) -> None:
        with pytest.raises(ValidationError, match="Loopback"):
            validate_host("127.0.0.1")

    def test_rejects_loopback_ipv6(self) -> None:
        with pytest.raises(ValidationError, match="Loopback"):
            validate_host("::1")

    def test_rejects_multicast(self) -> None:
        with pytest.raises(ValidationError, match="Multicast"):
            validate_host("224.0.0.1")

    def test_rejects_unspecified(self) -> None:
        with pytest.raises(ValidationError, match="Unspecified"):
            validate_host("0.0.0.0")

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValidationError, match="empty"):
            validate_host("")

    def test_rejects_whitespace_only(self) -> None:
        with pytest.raises(ValidationError, match="empty"):
            validate_host("   ")

    def test_rejects_invalid_string(self) -> None:
        with pytest.raises(ValidationError, match="Invalid host"):
            validate_host("not-a-valid-host-!!!")

    def test_accepts_private_ipv4_with_warning(self, caplog) -> None:
        import logging

        caplog.set_level(logging.WARNING)
        result = validate_host("192.168.1.1")
        assert result == "192.168.1.1"
        assert any("private" in r.message.lower() for r in caplog.records)

    def test_strips_whitespace(self) -> None:
        assert validate_host("  203.0.113.1  ") == "203.0.113.1"


class TestValidatePort:
    """Port number validation."""

    def test_valid_privileged_port(self) -> None:
        assert validate_port(443) == 443

    def test_valid_unprivileged_port(self) -> None:
        assert validate_port(8080) == 8080

    def test_valid_port_from_string(self) -> None:
        assert validate_port("51820") == 51820

    def test_rejects_zero(self) -> None:
        with pytest.raises(ValidationError, match="range"):
            validate_port(0)

    def test_rejects_above_65535(self) -> None:
        with pytest.raises(ValidationError, match="range"):
            validate_port(65536)

    def test_rejects_negative(self) -> None:
        with pytest.raises(ValidationError, match="range"):
            validate_port(-1)

    def test_rejects_non_numeric(self) -> None:
        with pytest.raises(ValidationError, match="integer"):
            validate_port("abc")

    def test_disallow_privileged_ports(self) -> None:
        with pytest.raises(ValidationError, match="range"):
            validate_port(80, allow_privileged=False)

    def test_allow_unprivileged_when_restricted(self) -> None:
        assert validate_port(8080, allow_privileged=False) == 8080

    def test_boundary_min_port(self) -> None:
        assert validate_port(1) == 1

    def test_boundary_max_port(self) -> None:
        assert validate_port(65535) == 65535


class TestValidateProtocol:
    """Protocol selection validation."""

    def test_valid_wireguard(self) -> None:
        assert validate_protocol("wireguard") == "wireguard"

    def test_valid_vless_reality(self) -> None:
        assert validate_protocol("vless-reality") == "vless-reality"

    def test_valid_hysteria2(self) -> None:
        assert validate_protocol("hysteria2") == "hysteria2"

    def test_valid_tuic(self) -> None:
        assert validate_protocol("tuic") == "tuic"

    def test_case_insensitive(self) -> None:
        assert validate_protocol("WIREGUARD") == "wireguard"

    def test_strips_whitespace(self) -> None:
        assert validate_protocol("  vless-reality  ") == "vless-reality"

    def test_rejects_unknown_protocol(self) -> None:
        with pytest.raises(ValidationError, match="Unsupported"):
            validate_protocol("openvpn")

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValidationError, match="Unsupported"):
            validate_protocol("")


class TestCheckPortAvailable:
    """Port availability checks."""

    def test_ephemeral_port_usually_free(self) -> None:
        # A high ephemeral port should be free in test environments
        result = check_port_available(54321, "127.0.0.1")
        assert result is True

    def test_same_port_twice_is_bound(self) -> None:
        """Bind a port, verify second check returns False."""
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        try:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
            # Now check — should be unavailable since we hold it
            result = check_port_available(port, "127.0.0.1")
            assert result is False
        finally:
            sock.close()
