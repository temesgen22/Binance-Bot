"""
Encryption service for API keys and secrets using Fernet (symmetric encryption).

Fernet uses AES-128 in CBC mode with HMAC-SHA256 for authentication.
This provides authenticated encryption ensuring both confidentiality and integrity.
"""
from __future__ import annotations

import base64
import secrets
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from loguru import logger


class EncryptionService:
    """Service for encrypting and decrypting sensitive data like API keys."""
    
    def __init__(self, encryption_key: Optional[str] = None):
        """
        Initialize encryption service.
        
        Args:
            encryption_key: Base64-encoded Fernet key. If None, will be loaded
                           from ENCRYPTION_KEY environment variable.
        
        Raises:
            ValueError: If encryption key is not provided and ENCRYPTION_KEY is not set.
        """
        if encryption_key is None:
            import os
            encryption_key = os.getenv("ENCRYPTION_KEY")
        
        if not encryption_key:
            raise ValueError(
                "ENCRYPTION_KEY environment variable must be set. "
                "Generate one using: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )
        
        # Validate and create Fernet instance
        try:
            # Ensure key is properly formatted (base64, 32 bytes when decoded)
            key_bytes = encryption_key.encode() if isinstance(encryption_key, str) else encryption_key
            # Fernet will raise ValueError if key is invalid
            self._fernet = Fernet(key_bytes)
        except (ValueError, TypeError) as e:
            raise ValueError(
                f"Invalid encryption key format. Must be a base64-encoded 32-byte key. Error: {e}"
            ) from e
    
    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt a plaintext string.
        
        Args:
            plaintext: The string to encrypt
        
        Returns:
            Base64-encoded encrypted string
        
        Raises:
            ValueError: If plaintext is empty or None
        """
        if not plaintext:
            raise ValueError("Cannot encrypt empty or None value")
        
        try:
            encrypted_bytes = self._fernet.encrypt(plaintext.encode('utf-8'))
            return encrypted_bytes.decode('utf-8')
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise ValueError(f"Failed to encrypt data: {e}") from e
    
    def decrypt(self, ciphertext: str) -> str:
        """
        Decrypt an encrypted string.
        
        Args:
            ciphertext: The base64-encoded encrypted string
        
        Returns:
            Decrypted plaintext string
        
        Raises:
            ValueError: If decryption fails (invalid token, wrong key, etc.)
        """
        if not ciphertext:
            raise ValueError("Cannot decrypt empty or None value")
        
        try:
            decrypted_bytes = self._fernet.decrypt(ciphertext.encode('utf-8'))
            return decrypted_bytes.decode('utf-8')
        except InvalidToken as e:
            logger.error(f"Decryption failed: Invalid token or wrong key")
            raise ValueError("Failed to decrypt data: Invalid token or wrong encryption key") from e
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise ValueError(f"Failed to decrypt data: {e}") from e
    
    @staticmethod
    def generate_key() -> str:
        """
        Generate a new Fernet encryption key.
        
        Returns:
            Base64-encoded encryption key string
        """
        key = Fernet.generate_key()
        return key.decode('utf-8')
    
    @staticmethod
    def derive_key_from_password(password: str, salt: Optional[bytes] = None) -> str:
        """
        Derive a Fernet key from a password using PBKDF2.
        
        This is useful if you want to derive the key from a master password.
        Note: The salt should be stored securely and reused for decryption.
        
        Args:
            password: Master password
            salt: Optional salt (if None, a random salt is generated)
        
        Returns:
            Base64-encoded encryption key
        """
        if salt is None:
            salt = secrets.token_bytes(16)
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key.decode('utf-8')


# Global encryption service instance (lazy initialization)
_encryption_service: Optional[EncryptionService] = None


def get_encryption_service() -> EncryptionService:
    """
    Get or create the global encryption service instance.
    
    Returns:
        EncryptionService instance
    
    Raises:
        ValueError: If ENCRYPTION_KEY is not configured
    """
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = EncryptionService()
    return _encryption_service


def encrypt_api_key(plaintext: str) -> str:
    """
    Convenience function to encrypt an API key.
    
    Args:
        plaintext: The API key to encrypt
    
    Returns:
        Encrypted API key string
    """
    return get_encryption_service().encrypt(plaintext)


def decrypt_api_key(ciphertext: str) -> str:
    """
    Convenience function to decrypt an API key.
    
    Args:
        ciphertext: The encrypted API key
    
    Returns:
        Decrypted API key string
    """
    return get_encryption_service().decrypt(ciphertext)

