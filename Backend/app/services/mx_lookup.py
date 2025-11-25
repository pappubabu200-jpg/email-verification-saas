# backend/app/services/mx_lookup.py

import dns.resolver
import dns.exception
import logging
from typing import List, Dict, Optional

from backend.app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------
# CONFIG
# ---------------------------------------------------

DNS_TIMEOUT = float(getattr(settings, "DNS_TIMEOUT", 5.0))
DNS_RETRIES = int(getattr(settings, "DNS_RETRIES", 2))

# Fallback resolvers (Google + Cloudflare)
DEFAULT_NAMESERVERS = [
    "1.1.1.1",    # Cloudflare
    "1.0.0.1",
    "8.8.8.8",    # Google
    "8.8.4.4",
]


# ---------------------------------------------------
# NORMALIZE MX HOST
# ---------------------------------------------------

def _normalize_host(host: str) -> str:
    """
    Clean MX hostname:
      - strip trailing dot
      - remove IPv6 [brackets]
      - lowercase always
    """
    if not host:
        return host

    host = host.strip().rstrip(".")

    # [IPv6] → IPv6
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]

    return host.lower()


# ---------------------------------------------------
# MAIN LOOKUP
# ---------------------------------------------------

def choose_mx_for_domain(domain: str) -> List[str]:
    """
    Production MX lookup with:
      ✔ fallback resolvers
      ✔ retries
      ✔ normalized hosts
      ✔ clean failure modes

    Returns:
      ["mx1.example.com", "mx2.example.net"]
    or:
      []
    """

    if not domain:
        return []

    domain = domain.lower().strip()
    logger.debug(f"[MX] lookup start for {domain}")

    # Create resolver
    resolver = dns.resolver.Resolver(configure=True)
    resolver.timeout = DNS_TIMEOUT
    resolver.lifetime = DNS_TIMEOUT * (DNS_RETRIES + 1)

    # Force fallback resolvers if system resolvers empty
    try:
        if not resolver.nameservers:
            resolver.nameservers = DEFAULT_NAMESERVERS
    except Exception:
        resolver.nameservers = DEFAULT_NAMESERVERS

    attempts = DNS_RETRIES + 1

    for attempt in range(attempts):

        try:
            answers = resolver.resolve(domain, "MX", lifetime=DNS_TIMEOUT)

            mx_pairs = []
            for r in answers:
                try:
                    preference = int(r.preference)
                    host = _normalize_host(str(r.exchange))
                except Exception:
                    preference = 100
                    host = _normalize_host(str(r))

                mx_pairs.append((preference, host))

            mx_pairs.sort(key=lambda x: x[0])
            hosts = [h for _, h in mx_pairs]

            if hosts:
                logger.debug(f"[MX] {domain} -> {hosts}")
                return hosts

        except dns.resolver.Timeout:
            logger.debug(f"[MX] timeout for {domain} (attempt {attempt+1}/{attempts})")
            continue

        except dns.resolver.NXDOMAIN:
            logger.debug(f"[MX] NXDOMAIN: {domain} does not exist")
            return []

        except dns.resolver.NoAnswer:
            logger.debug(f"[MX] no MX records for {domain}")
            return []

        except dns.exception.DNSException as e:
            logger.debug(f"[MX] DNSException for {domain}: {e}")
            continue

        except Exception as e:
            logger.debug(f"[MX] Unexpected MX lookup error for {domain}: {e}")
            continue

    # All retries failed
    logger.debug(f"[MX] all attempts failed for {domain}")
    return []


# ---------------------------------------------------
# OPTIONAL: DNS HEALTH CHECK
# ---------------------------------------------------

def dns_health_check() -> Dict[str, str]:
    """
    Simple diagnostic to ensure DNS works normally.
    """
    try:
        resolver = dns.resolver.Resolver()
        resolver.timeout = DNS_TIMEOUT
        resolver.lifetime = DNS_TIMEOUT
        resolver.resolve("gmail.com", "MX")
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "msg": str(e)}
