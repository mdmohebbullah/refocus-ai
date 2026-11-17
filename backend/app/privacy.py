"""Exclusion rules. Excluded items never reach the AI context (see ai/context.py)."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from .models import PrivacySettings

# Default sensitive categories (users may remove individual entries or add their own).
DEFAULT_SENSITIVE_DOMAINS: dict[str, list[str]] = {
    "Banking, payment and investment": [
        "paypal.com", "venmo.com", "stripe.com", "chase.com", "bankofamerica.com", "wellsfargo.com",
        "citi.com", "capitalone.com", "americanexpress.com", "discover.com", "usbank.com", "schwab.com",
        "fidelity.com", "vanguard.com", "robinhood.com", "coinbase.com", "wise.com", "zelle.com",
    ],
    "Email and messaging": [
        "mail.google.com", "outlook.live.com", "outlook.office.com", "outlook.office365.com",
        "mail.yahoo.com", "proton.me", "web.whatsapp.com", "messenger.com", "web.telegram.org",
        "discord.com", "slack.com", "teams.microsoft.com", "signal.org",
    ],
    "Health, patient and insurance": [
        "mychart.com", "patientportal.com", "healthcare.gov", "kp.org", "anthem.com", "aetna.com",
        "cigna.com", "uhc.com", "bcbs.com", "zocdoc.com", "teladoc.com",
    ],
    "Password managers": [
        "1password.com", "lastpass.com", "bitwarden.com", "dashlane.com", "keepersecurity.com",
    ],
    "Government, tax and identity": [
        "irs.gov", "ssa.gov", "login.gov", "id.me", "usps.com", "dmv.org", "uscis.gov", "turbotax.intuit.com",
    ],
}

# URL patterns for checkout, payment and sign-in pages on any site.
SENSITIVE_PATH_PATTERNS = [
    re.compile(p, re.I)
    for p in [r"/checkout", r"/payment", r"/billing", r"/cart\b", r"/login", r"/signin", r"/sign-in",
              r"/oauth", r"/password", r"/account/security", r"/wallet"]
]


def all_default_domains() -> list[str]:
    return sorted({d for ds in DEFAULT_SENSITIVE_DOMAINS.values() for d in ds})


def domain_of(url: str | None) -> str:
    if not url:
        return ""
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return ""
    return host.lower().removeprefix("www.")


def _matches(domain: str, rules: list[str]) -> bool:
    return any(domain == r or domain.endswith("." + r) for r in rules)


def effective_exclusions(priv: PrivacySettings | None) -> list[str]:
    removed = set(priv.removed_default_exclusions or []) if priv else set()
    user = list(priv.excluded_domains or []) if priv else []
    return sorted({d for d in all_default_domains() if d not in removed} | {u.lower().removeprefix("www.") for u in user})


def is_sensitive_url(url: str | None) -> bool:
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return True
    if parsed.scheme not in ("http", "https"):
        return True  # chrome://, file://, about: … never collected
    return any(p.search(parsed.path or "") for p in SENSITIVE_PATH_PATTERNS)


def is_excluded(url: str | None, priv: PrivacySettings | None, has_password_field: bool = False) -> bool:
    if has_password_field:
        return True
    d = domain_of(url)
    if not d:
        return True
    if _matches(d, effective_exclusions(priv)):
        return True
    return is_sensitive_url(url)
