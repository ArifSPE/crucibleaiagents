"""
Secrets Manager for AgentFlow
Handles encryption and decryption of sensitive package secrets.
"""
import os
import base64
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken


class SecretsManager:
    """Manages encryption and decryption of secrets using Fernet symmetric encryption."""
    
    def __init__(self, encryption_key: Optional[str] = None):
        """
        Initialize the secrets manager with an encryption key.
        
        Args:
            encryption_key: Base64-encoded Fernet key. If None, reads from SECRETS_ENCRYPTION_KEY env var.
        
        Raises:
            ValueError: If no encryption key is provided or found in environment.
        """
        key = encryption_key or os.getenv("SECRETS_ENCRYPTION_KEY")
        
        if not key:
            raise ValueError(
                "SECRETS_ENCRYPTION_KEY environment variable must be set. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        
        try:
            self.cipher = Fernet(key.encode())
        except Exception as e:
            raise ValueError(f"Invalid encryption key format: {e}")
    
    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt a plaintext secret value.
        
        Args:
            plaintext: The secret value to encrypt.
        
        Returns:
            Base64-encoded encrypted value suitable for database storage.
        """
        if not plaintext:
            return ""
        
        try:
            encrypted_bytes = self.cipher.encrypt(plaintext.encode('utf-8'))
            return base64.b64encode(encrypted_bytes).decode('utf-8')
        except Exception as e:
            raise ValueError(f"Failed to encrypt secret: {e}")
    
    def decrypt(self, encrypted_value: str) -> str:
        """
        Decrypt an encrypted secret value.
        
        Args:
            encrypted_value: Base64-encoded encrypted value from database.
        
        Returns:
            The original plaintext secret value.
        
        Raises:
            ValueError: If decryption fails (invalid key or corrupted data).
        """
        if not encrypted_value:
            return ""
        
        try:
            encrypted_bytes = base64.b64decode(encrypted_value.encode('utf-8'))
            decrypted_bytes = self.cipher.decrypt(encrypted_bytes)
            return decrypted_bytes.decode('utf-8')
        except InvalidToken:
            raise ValueError("Failed to decrypt secret: Invalid encryption key or corrupted data")
        except Exception as e:
            raise ValueError(f"Failed to decrypt secret: {e}")
    
    @staticmethod
    def generate_key() -> str:
        """
        Generate a new Fernet encryption key.
        
        Returns:
            A base64-encoded Fernet key suitable for use as SECRETS_ENCRYPTION_KEY.
        """
        return Fernet.generate_key().decode('utf-8')


# Global instance for convenience
_secrets_manager: Optional[SecretsManager] = None


def get_secrets_manager() -> SecretsManager:
    """
    Get or create the global secrets manager instance.
    
    Returns:
        The global SecretsManager instance.
    """
    global _secrets_manager
    if _secrets_manager is None:
        _secrets_manager = SecretsManager()
    return _secrets_manager
