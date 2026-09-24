"""Shared fixtures."""
from __future__ import annotations

import socket
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations, mock_async_zeroconf):
    """Load custom_components/ in every test, with HA's zeroconf dependency mocked."""
    return


@pytest.fixture
def free_port(socket_enabled) -> int:
    """An unused TCP port on this machine."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def no_mdns():
    """Don't send multicast from tests."""
    with (
        patch("custom_components.fronius_virtual_inverter.FroniusMDNSAnnouncer.async_start"),
        patch("custom_components.fronius_virtual_inverter.RawMDNSAnnouncer.async_start"),
    ):
        yield
