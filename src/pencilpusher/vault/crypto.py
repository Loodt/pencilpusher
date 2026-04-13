"""Encryption layer for the vault. Uses Fernet (AES-128-CBC) with password-derived keys."""

import base64
import os
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

SALT_FILE = "vault.salt"
KEY_CHECK_FILE = "vault.check"
KEY_CHECK_PLAINTEXT = b"pencilpusher-vault-key-check"


def _derive_key(password: str, salt: bytes) -> bytes:
    """Derive a Fernet key from a password and salt using PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=600_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))


def init_vault_encryption(vault_dir: Path, password: str) -> Fernet:
    """Initialize vault encryption. Creates salt if first time, verifies password if existing."""
    salt_path = vault_dir / SALT_FILE
    check_path = vault_dir / KEY_CHECK_FILE

    if salt_path.exists():
        # Existing vault — verify password
        salt = salt_path.read_bytes()
        key = _derive_key(password, salt)
        fernet = Fernet(key)

        if check_path.exists():
            try:
                fernet.decrypt(check_path.read_bytes())
            except Exception:
                raise ValueError("Wrong password for this vault.")
        return fernet
    else:
        # New vault — create salt and key check file
        salt = os.urandom(16)
        vault_dir.mkdir(parents=True, exist_ok=True)
        salt_path.write_bytes(salt)

        key = _derive_key(password, salt)
        fernet = Fernet(key)
        check_path.write_bytes(fernet.encrypt(KEY_CHECK_PLAINTEXT))
        return fernet


def encrypt_file(fernet: Fernet, source_path: Path, dest_path: Path) -> None:
    """Encrypt a file and write to dest_path."""
    plaintext = source_path.read_bytes()
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(fernet.encrypt(plaintext))


def decrypt_file(fernet: Fernet, encrypted_path: Path) -> bytes:
    """Decrypt a file and return the plaintext bytes."""
    return fernet.decrypt(encrypted_path.read_bytes())


def encrypt_text(fernet: Fernet, text: str) -> bytes:
    """Encrypt a text string."""
    return fernet.encrypt(text.encode("utf-8"))


def decrypt_text(fernet: Fernet, token: bytes) -> str:
    """Decrypt to a text string."""
    return fernet.decrypt(token).decode("utf-8")
