"""Exact proxy sources; never trust all private Docker networks."""
import ipaddress
import os
from pathlib import Path
import socket
from threading import Lock, Thread
import time

_DNS_REFRESH_SECONDS = 30.0
_DNS_MAX_STALE_SECONDS = 60.0
_DNS_RETRY_SECONDS = 5.0
_dns_lock = Lock()
_cached_hosts: set[str] = set()
_hosts_config: tuple[str, ...] = ()
_refresh_at = 0.0
_valid_until = 0.0
_refreshing = False


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
    global _cached_hosts, _hosts_config, _refresh_at, _valid_until, _refreshing
    result = set()
    if os.getenv('TRUST_DOCKER_GATEWAY') == 'true' and Path('/.dockerenv').exists():
        result.update(docker_gateways(Path('/proc/net/route').read_text()))

    hosts = tuple(host.strip() for host in os.getenv('TRUSTED_PROXY_HOSTS', '').split(',') if host.strip())
    now = time.monotonic()
    with _dns_lock:
        if hosts != _hosts_config:
            _hosts_config = hosts
            _cached_hosts = set()
            _refresh_at = 0.0
            _valid_until = 0.0
        if hosts and now >= _refresh_at and not _refreshing:
            _refreshing = True
            Thread(
                target=_refresh_proxy_hosts,
                args=(hosts,),
                daemon=True,
                name='trusted-proxy-dns-refresh',
            ).start()
        if now < _valid_until:
            result.update(_cached_hosts)
    return result


def _refresh_proxy_hosts(hosts):
    """Resolve proxy aliases off-request; a slow Docker DNS lookup must not stall login."""
    global _cached_hosts, _refresh_at, _valid_until, _refreshing
    resolved = set()
    success = True
    for host in hosts:
        try:
            resolved.update(entry[4][0] for entry in socket.getaddrinfo(host, None))
        except OSError:
            success = False
    with _dns_lock:
        now = time.monotonic()
        if success:
            # Empty results fail closed. Keep known addresses only until the
            # short stale window expires while refreshing slow DNS in parallel.
            _cached_hosts = resolved
            _refresh_at = now + _DNS_REFRESH_SECONDS
            _valid_until = now + _DNS_MAX_STALE_SECONDS if resolved else now
        else:
            _refresh_at = now + _DNS_RETRY_SECONDS
            if now >= _valid_until:
                _cached_hosts = set()
        _refreshing = False


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
