import socket
import ipaddress
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

PRIVATE_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
]

def _is_private_ip(ip: str) -> bool:
    try:
        ip_obj = ipaddress.ip_address(ip)
        return any(ip_obj in net for net in PRIVATE_RANGES)
    except Exception:
        return False

def resolve_a_for_host(host: str) -> Optional[str]:
    try:
        infos = socket.getaddrinfo(host, None)
        # pick first IPv4 address if available
        for fam, _, _, _, sockaddr in infos:
            if fam == socket.AF_INET:
                return sockaddr[0]
        # fallback to first address
        return infos[0][4][0]
    except Exception as e:
        logger.debug("resolve_a_for_host failed %s -> %s", host, e)
        return None

def get_mx_ip_info(mx_host: str) -> Dict:
    """
    Resolve MX host to IP and return basic intelligence:
      - ip, is_private, reverse_dns, basic_score (higher = better)
    Note: this is local heuristics only. For production use integrate with third-party IP reputation APIs.
    """
    ip = resolve_a_for_host(mx_host)
    info = {"mx_host": mx_host, "ip": ip, "is_private": False, "reverse_dns": None, "score": 50}
    if ip:
        try:
            info["is_private"] = _is_private_ip(ip)
            try:
                r = socket.gethostbyaddr(ip)
                info["reverse_dns"] = r[0]
            except Exception:
                info["reverse_dns"] = None
            # scoring heuristics: private IP = very bad; presence of reverse dns = good
            if info["is_private"]:
                info["score"] = 10
            else:
                info["score"] = 60
                if info["reverse_dns"]:
                    info["score"] += 20
        except Exception:
            pass
    return info
