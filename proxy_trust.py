"""Exact proxy sources; never trust all private Docker networks."""
import ipaddress
import os
from pathlib import Path
import socket
import time

_cached_hosts = (0.0, set())


def docker_gateways(route):
    result = set()
    for line in route.splitlines():
        fields = line.split()
        if len(fields) < 4 or fields[1] != '00000000':
            continue
        try:
            if int(fields[3], 16) & 2:
                result.add(str(ipaddress.ip_address(bytes.fromhex(fields[2])[::-1])))
        except ValueError:
            pass
    return result


def extra_trusted_addresses():
    global _cached_hosts
    result = set()
    if os.getenv('TRUST_DOCKER_GATEWAY') == 'true' and Path('/.dockerenv').exists():
        result.update(docker_gateways(Path('/proc/net/route').read_text()))
    if time.monotonic() >= _cached_hosts[0]:
        resolved = set()
        for host in os.getenv('TRUSTED_PROXY_HOSTS', '').split(','):
            if not host.strip():
                continue
            try:
                resolved.update(entry[4][0] for entry in socket.getaddrinfo(host.strip(), None))
            except OSError:
                pass
        _cached_hosts = (time.monotonic() + 1, resolved)
    return result | _cached_hosts[1]


def client_ip(peer, forwarded, trusted):
    def normalize(value):
        address = ipaddress.ip_address(value)
        return str(address.ipv4_mapped if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped else address)
    try:
        peer = normalize(peer)
        if not trusted(peer) or not forwarded:
            return peer
        chain = [normalize(value.strip()) for value in forwarded.split(',')]
    except ValueError:
        return peer
    current = peer
    for candidate in reversed(chain):
        if not trusted(current):
            break
        current = candidate
    return current
