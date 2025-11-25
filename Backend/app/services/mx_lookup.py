# backend/app/services/mx_lookup.py

import dns.resolver
import dns.exception
import logging
from typing import List, Dict, Optional

from backend.app.config import settings

logger = logging.getLogger(__name__)

# -----------------------------------------------
# CONFIG
# -----------------------------------------------

DNS_TIMEOUT = float(getattr(settings, "DNS_TIMEOUT", 5.0))
DNS_RETRIES = int(getattr(settings, "DNS_RETRIES", 2))

# Fallback resolvers (Google + Cloudflare)
DEFAULT_NAMESERVERS = [
    "1.1.1.1",       # Cloudflare
    "8.8.8.8",       # Google
    "8.8.4.4",
    "1.0.0.1"
]


# -----------------------------------------------
# Normalize MX host (strip trailing dot, fix IPv6)
# -----------------------------------------------

def _normalize_host(host: str) -> str:
    if not host:
        return host
    host = host.strip().rstrip(".")
    if host.startswith("[") and host.endswith("]"):
        # remove bracketed IPv6 style
        host = host[1:-1]
    return host.lower()


# -----------------------------------------------
# Main MX Lookup
# -----------------------------------------------

def choose_mx_for_domain(domain: str) -> List[str]:
    """
    Returns list of MX hosts sorted by preference.
    Always returns *clean normalized* hostnames.
    On failure → returns empty list.
    """
    if not domain:
        return []

    domain = domain.lower().strip()

    # Prepare resolver
    resolver = dns.resolver.Resolver(configure=True)
    resolver.timeout = DNS_TIMEOUT
    resolver.lifetime = DNS_TIMEOUT * (DNS_RETRIES + 1)

    # Inject fallback resolvers as backup
    try:
        if not resolver.nameservers:
            resolver.nameservers = DEFAULT_NAMESERVERS
    except Exception:
        resolver.nameservers = DEFAULT_NAMESERVERS

    # Try multiple attempts
    for attempt in range(DNS_RETRIES + 1):

        try:
            answers = resolver.resolve(domain, "MX", lifetime=DNS_TIMEOUT)

            mx_pairs = []
            for r in answers:
                try:
                    pref = int(r.preference)
                    host = _normalize_host(str(r.exchange))
                except Exception:
                    pref = 100
                    host = _normalize_host(str(r))

                mx_pairs.append((pref, host))

            mx_pairs.sort(key=lambda x: x[0])
            hosts = [h for _, h in mx_pairs]

            if hosts:
                return hosts

        except dns.resolver.Timeout:
            logger.debug(f"MX timeout for {domain} (attempt {attempt+1})")
            continue
        except dns.resolver.NXDOMAIN:
            logger.debug(f"NXDOMAIN: {domain} does not exist")
            return []
        except dns.resolver.NoAnswer:
            logger.debug(f"No MX records for {domain}")
            return []
        except dns.exception.DNSException as e:
            logger.debug(f"DNS error for {domain}: {e}")
            continue
        except Exception as e:
            logger.debug(f"Unknown MX error for {domain}: {e}")
            continue

    # All attempts failed
    return []


# -----------------------------------------------
# Optional: Quick DNS health check (for diagnostics)
# -----------------------------------------------

def dns_health_check() -> Dict[str, str]:
    try:
        resolver = dns.resolver.Resolver()
        resolver.timeout = DNS_TIMEOUT
        resolver.lifetime = DNS_TIMEOUT
        resolver.resolve("gmail.com", "MX")
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "msg": str(e)}
