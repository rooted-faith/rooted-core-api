"""
Client IP resolution shared by rate limiting (ROO-60) and later audit / refresh-token IP (ROO-65).

When TRUSTED_CLIENT_IP_HEADER is unset, only the transport peer is used.
When set, that single header may supply the client IP if it is a valid address;
otherwise the peer is used and a warning is logged. X-Forwarded-For is never
trusted implicitly.
"""

from __future__ import annotations

import ipaddress
import logging
from typing import Optional

from starlette.requests import HTTPConnection
from starlette.types import Scope

logger = logging.getLogger(__name__)


def canonical_ip(value: str) -> Optional[str]:
    """
    One IPv4/IPv6 address in canonical text form; IPv4-mapped IPv6 becomes IPv4.
    :param value:
    :return: None for lists, zone IDs, hostnames, or empty values
    """
    if "%" in value:
        return None
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return str(address.ipv4_mapped)
    return str(address)


def transport_peer_ip(scope: Scope) -> Optional[str]:
    """
    The canonical transport peer address, or None when absent or not an IP.
    :param scope:
    :return:
    """
    client = scope.get("client")
    return canonical_ip(client[0]) if client else None


def resolved_client_ip(connection: HTTPConnection, *, trusted_header: Optional[str] = None) -> Optional[str]:
    """
    Resolve the client IP for rate limiting and related uses.

    :param connection: request or websocket connection
    :param trusted_header: optional single header name (e.g. True-Client-IP); unset means peer only
    :return: canonical IP string, or None when no peer and no usable header
    """
    peer = transport_peer_ip(connection.scope)

    if not trusted_header:
        return peer

    raw = connection.headers.get(trusted_header)
    if raw is None or raw.strip() == "":
        logger.warning("Trusted client IP header %s is missing; using connection IP", trusted_header)
        return peer

    # A trusted header must be a single IP, not a forwarded list.
    if "," in raw:
        logger.warning("Trusted client IP header %s is invalid; using connection IP", trusted_header)
        return peer

    header_ip = canonical_ip(raw)
    if header_ip is None:
        logger.warning("Trusted client IP header %s is invalid; using connection IP", trusted_header)
        return peer

    return header_ip
