"""Configuration management for pencilpusher."""

import os
from pathlib import Path

import yaml

DEFAULT_VAULT_DIR = Path.home() / ".pencilpusher"

# Wiki page categories — each becomes a markdown file in the vault wiki/
WIKI_PAGES = [
    "identity",      # Name, ID number, passport, date of birth, nationality
    "banking",       # Bank accounts, branch codes, SWIFT/BIC
    "company",       # Company name, registration, VAT, directors, B-BBEE
    "addresses",     # Physical, postal, registered addresses
    "contacts",      # Phone numbers, email addresses, emergency contacts
    "tax",           # Tax numbers, returns info, tax practitioner
    "vehicles",      # Vehicle registrations, license discs
    "medical",       # Medical aid, doctor details, allergies
    "education",     # Qualifications, institutions, dates
    "employment",    # Employment history, current employer
    "legal",         # Powers of attorney, trusts, wills
    "insurance",     # Policies, brokers, claim numbers
]


def get_vault_dir() -> Path:
    """Get the vault directory, respecting PENCILPUSHER_VAULT env var."""
    env_path = os.environ.get("PENCILPUSHER_VAULT")
    if env_path:
        return Path(env_path)
    return DEFAULT_VAULT_DIR


def get_config_path() -> Path:
    return get_vault_dir() / "config.yaml"


def load_config() -> dict:
    """Load config from vault directory. Returns defaults if no config file."""
    config_path = get_config_path()
    defaults = {
        "vault_dir": str(get_vault_dir()),
        "model": "claude-sonnet-4-6",
        "vision_model": "claude-sonnet-4-6",
        "encryption": False,
        "auto_lint": True,
    }
    if config_path.exists():
        with open(config_path) as f:
            user_config = yaml.safe_load(f) or {}
        defaults.update(user_config)
    return defaults


def save_config(config: dict) -> None:
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
