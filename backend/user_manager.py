# -*- coding: utf-8 -*-
"""
User management module for Motion Frontend.
Handles user authentication, password hashing with bcrypt, and user CRUD operations.

Version: 0.1.0
"""

import json
import logging
import secrets
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Try to import bcrypt for secure password hashing
try:
    import bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    BCRYPT_AVAILABLE = False
    logger.warning("bcrypt not available - using SHA256 fallback (less secure)")

# Fallback to hashlib if bcrypt not available
import hashlib


class UserRole(Enum):
    """User roles with different permission levels."""
    ADMIN = "admin"      # Full access - can manage users, change all settings
    USER = "user"        # Limited access - view cameras, limited settings
    VIEWER = "viewer"    # Read-only access - view cameras only


@dataclass
class User:
    """User account data."""
    username: str
    password_hash: str
    role: UserRole = UserRole.USER
    enabled: bool = True
    must_change_password: bool = False
    created_at: str = ""
    last_login: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize user to dictionary (excluding sensitive data for API)."""
        return {
            "username": self.username,
            "role": self.role.value,
            "enabled": self.enabled,
            "must_change_password": self.must_change_password,
            "created_at": self.created_at,
            "last_login": self.last_login,
        }
    
    def to_storage_dict(self) -> Dict[str, Any]:
        """Serialize user to dictionary for storage (includes password hash)."""
        return {
            "username": self.username,
            "password_hash": self.password_hash,
            "role": self.role.value,
            "enabled": self.enabled,
            "must_change_password": self.must_change_password,
            "created_at": self.created_at,
            "last_login": self.last_login,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "User":
        """Deserialize user from dictionary."""
        return cls(
            username=data.get("username", ""),
            password_hash=data.get("password_hash", ""),
            role=UserRole(data.get("role", "user")),
            enabled=data.get("enabled", True),
            must_change_password=data.get("must_change_password", False),
            created_at=data.get("created_at", ""),
            last_login=data.get("last_login", ""),
        )


class UserManager:
    """
    Manages user accounts with secure password hashing.
    
    Features:
    - bcrypt password hashing (with SHA256 fallback)
    - User CRUD operations
    - Role-based access control
    - Password change enforcement
    - Persistent storage in JSON file
    """
    
    DEFAULT_USERS_PATH = Path("config/users.json")
    
    # bcrypt work factor (higher = more secure but slower)
    BCRYPT_ROUNDS = 12
    
    def __init__(self, users_path: Optional[Path] = None) -> None:
        self._users_path = users_path or self.DEFAULT_USERS_PATH
        self._users: Dict[str, User] = {}
        self._dirty = False
        
        self._load_users()
        
        # Ensure both admin and user accounts exist
        self._ensure_default_users()
    
    def _load_users(self) -> None:
        """Load users from JSON file."""
        try:
            if self._users_path.exists():
                with self._users_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    for username, user_data in data.get("users", {}).items():
                        self._users[username] = User.from_dict(user_data)
                logger.info("Loaded %d users from %s", len(self._users), self._users_path)
            else:
                logger.info("Users file not found, will create with defaults")
        except Exception as e:
            logger.error("Failed to load users: %s", e)
            self._users = {}
    
    def _save_users(self) -> None:
        """Save users to JSON file."""
        try:
            self._users_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "version": "1.0",
                "users": {
                    username: user.to_storage_dict()
                    for username, user in self._users.items()
                }
            }
            with self._users_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self._dirty = False
            logger.debug("Users saved to %s", self._users_path)
        except Exception as e:
            logger.error("Failed to save users: %s", e)
    
    def _create_default_admin(self) -> None:
        """Create default admin user with default password."""
        from datetime import datetime
        
        logger.info("Creating default admin user")
        self._users["admin"] = User(
            username="admin",
            password_hash=self._hash_password("admin"),
            role=UserRole.ADMIN,
            enabled=True,
            must_change_password=True,  # Force password change on first login
            created_at=datetime.now().isoformat(),
        )
        self._save_users()
    
    def _create_default_user(self) -> None:
        """Create default user account with default password."""
        from datetime import datetime
        
        logger.info("Creating default user account")
        self._users["user"] = User(
            username="user",
            password_hash=self._hash_password("user"),
            role=UserRole.USER,
            enabled=True,
            must_change_password=True,  # Force password change on first login
            created_at=datetime.now().isoformat(),
        )
        self._save_users()
    
    def _ensure_default_users(self) -> None:
        """Ensure both admin and user accounts exist."""
        created = False
        
        # Ensure admin exists
        if "admin" not in self._users:
            from datetime import datetime
            logger.info("Creating default admin user")
            self._users["admin"] = User(
                username="admin",
                password_hash=self._hash_password("admin"),
                role=UserRole.ADMIN,
                enabled=True,
                must_change_password=True,
                created_at=datetime.now().isoformat(),
            )
            created = True
        
        # Ensure user exists
        if "user" not in self._users:
            from datetime import datetime
            logger.info("Creating default user account")
            self._users["user"] = User(
                username="user",
                password_hash=self._hash_password("user"),
                role=UserRole.USER,
                enabled=True,
                must_change_password=True,
                created_at=datetime.now().isoformat(),
            )
            created = True
        
        if created:
            self._save_users()
    
    def _hash_password(self, password: str) -> str:
        """Hash a password using bcrypt (or SHA256 fallback)."""
        if BCRYPT_AVAILABLE:
            # bcrypt handles salting automatically
            salt = bcrypt.gensalt(rounds=self.BCRYPT_ROUNDS)
            hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
            return hashed.decode("utf-8")
        else:
            # Fallback to SHA256 with a random salt prefix
            salt = secrets.token_hex(16)
            hash_input = f"{salt}:{password}"
            hashed = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
            return f"sha256:{salt}:{hashed}"
    
    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify a password against its hash."""
        if not password_hash:
            return False
        
        # Check if it's a bcrypt hash (starts with $2)
        if password_hash.startswith("$2"):
            if BCRYPT_AVAILABLE:
                try:
                    return bcrypt.checkpw(
                        password.encode("utf-8"),
                        password_hash.encode("utf-8")
                    )
                except Exception:
                    return False
            else:
                logger.warning("bcrypt hash found but bcrypt not available")
                return False
        
        # Check if it's a SHA256 hash with salt prefix
        elif password_hash.startswith("sha256:"):
            parts = password_hash.split(":", 2)
            if len(parts) == 3:
                _, salt, stored_hash = parts
                hash_input = f"{salt}:{password}"
                computed_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
                return computed_hash == stored_hash
            return False
        
        # Legacy: plain SHA256 without salt (old format)
        else:
            computed_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
            return computed_hash == password_hash
    
    def authenticate(self, username: str, password: str) -> Optional[User]:
        """
        Authenticate a user with username and password.
        
        Returns:
            User object if authentication successful, None otherwise.
        """
        user = self._users.get(username)
        if not user:
            logger.debug("Authentication failed: user '%s' not found", username)
            return None
        
        if not user.enabled:
            logger.debug("Authentication failed: user '%s' is disabled", username)
            return None
        
        if not self._verify_password(password, user.password_hash):
            logger.debug("Authentication failed: invalid password for '%s'", username)
            return None
        
        # Update last login time
        from datetime import datetime
        user.last_login = datetime.now().isoformat()
        self._save_users()
        
        logger.info("User '%s' authenticated successfully", username)
        return user
    
    def verify_credentials(self, username: str, password: str) -> bool:
        """
        Verify user credentials without updating last_login.
        Used for stream authentication.
        
        Args:
            username: The username to verify.
            password: The password to verify.
            
        Returns:
            True if credentials are valid, False otherwise.
        """
        user = self._users.get(username)
        if not user:
            logger.debug("Credential verification failed: user '%s' not found", username)
            return False
        
        if not user.enabled:
            logger.debug("Credential verification failed: user '%s' is disabled", username)
            return False
        
        if not self._verify_password(password, user.password_hash):
            logger.debug("Credential verification failed: invalid password for '%s'", username)
            return False
        
        logger.debug("Credentials verified for user '%s'", username)
        return True
    
    def get_user(self, username: str) -> Optional[User]:
        """Get a user by username."""
        return self._users.get(username)
    
    def list_users(self) -> List[Dict[str, Any]]:
        """List all users (without password hashes)."""
        return [user.to_dict() for user in self._users.values()]
    
    def create_user(
        self,
        username: str,
        password: str,
        role: UserRole = UserRole.USER,
        must_change_password: bool = False
    ) -> Optional[User]:
        """
        Create a new user.
        
        Returns:
            Created User object, or None if username already exists.
        """
        if username in self._users:
            logger.warning("Cannot create user: '%s' already exists", username)
            return None
        
        if not username or not password:
            logger.warning("Cannot create user: username and password required")
            return None
        
        from datetime import datetime
        
        user = User(
            username=username,
            password_hash=self._hash_password(password),
            role=role,
            enabled=True,
            must_change_password=must_change_password,
            created_at=datetime.now().isoformat(),
        )
        self._users[username] = user
        self._save_users()
        
        logger.info("Created user '%s' with role '%s'", username, role.value)
        return user
    
    def update_user(
        self,
        username: str,
        role: Optional[UserRole] = None,
        enabled: Optional[bool] = None,
        must_change_password: Optional[bool] = None
    ) -> Optional[User]:
        """
        Update user properties (not password).
        
        Returns:
            Updated User object, or None if user not found.
        """
        user = self._users.get(username)
        if not user:
            return None
        
        if role is not None:
            user.role = role
        if enabled is not None:
            user.enabled = enabled
        if must_change_password is not None:
            user.must_change_password = must_change_password
        
        self._save_users()
        logger.info("Updated user '%s'", username)
        return user
    
    def change_password(
        self,
        username: str,
        current_password: str,
        new_password: str
    ) -> Dict[str, Any]:
        """
        Change a user's password (requires current password verification).
        
        Returns:
            Dict with 'success' and optional 'error' message.
        """
        user = self._users.get(username)
        if not user:
            return {"success": False, "error": "Utilisateur non trouvé"}
        
        # Verify current password
        if not self._verify_password(current_password, user.password_hash):
            return {"success": False, "error": "Mot de passe actuel incorrect"}
        
        # Validate new password
        if len(new_password) < 4:
            return {"success": False, "error": "Le nouveau mot de passe doit contenir au moins 4 caractères"}
        
        if new_password == current_password:
            return {"success": False, "error": "Le nouveau mot de passe doit être différent de l'ancien"}
        
        # Update password
        user.password_hash = self._hash_password(new_password)
        user.must_change_password = False
        self._save_users()
        
        logger.info("Password changed for user '%s'", username)
        return {"success": True}
    
    def set_password(self, username: str, new_password: str, must_change: bool = False) -> Tuple[bool, str]:
        """
        Set a user's password directly (for internal/UI use).
        
        Args:
            username: The username to update.
            new_password: The new password to set.
            must_change: Whether to force password change on next login.
            
        Returns:
            Tuple of (success, message).
        """
        user = self._users.get(username)
        if not user:
            return (False, "Utilisateur non trouvé")
        
        if len(new_password) < 4:
            return (False, "Le mot de passe doit contenir au moins 4 caractères")
        
        user.password_hash = self._hash_password(new_password)
        user.must_change_password = must_change
        self._save_users()
        
        logger.info("Password set for user '%s'", username)
        return (True, "Mot de passe mis à jour")
    
    def admin_reset_password(
        self,
        admin_username: str,
        target_username: str,
        new_password: str
    ) -> Dict[str, Any]:
        """
        Admin-initiated password reset (no current password required).
        
        Returns:
            Dict with 'success' and optional 'error' message.
        """
        admin = self._users.get(admin_username)
        if not admin or admin.role != UserRole.ADMIN:
            return {"success": False, "error": "Droits d'administrateur requis"}
        
        user = self._users.get(target_username)
        if not user:
            return {"success": False, "error": "Utilisateur non trouvé"}
        
        if len(new_password) < 4:
            return {"success": False, "error": "Le mot de passe doit contenir au moins 4 caractères"}
        
        user.password_hash = self._hash_password(new_password)
        user.must_change_password = True  # Force user to change password
        self._save_users()
        
        logger.info("Admin '%s' reset password for user '%s'", admin_username, target_username)
        return {"success": True}
    
    def delete_user(self, username: str) -> bool:
        """
        Delete a user.
        
        Returns:
            True if deleted, False if user not found or is the last admin.
        """
        if username not in self._users:
            return False
        
        user = self._users[username]
        
        # Prevent deleting the last admin
        if user.role == UserRole.ADMIN:
            admin_count = sum(1 for u in self._users.values() if u.role == UserRole.ADMIN)
            if admin_count <= 1:
                logger.warning("Cannot delete last admin user")
                return False
        
        del self._users[username]
        self._save_users()
        
        logger.info("Deleted user '%s'", username)
        return True
    
    def is_bcrypt_available(self) -> bool:
        """Check if bcrypt is available for secure password hashing."""
        return BCRYPT_AVAILABLE
    
    def migrate_legacy_passwords(self) -> int:
        """
        Migrate legacy SHA256 passwords to bcrypt if available.
        
        Returns:
            Number of passwords migrated.
        """
        if not BCRYPT_AVAILABLE:
            return 0
        
        migrated = 0
        for user in self._users.values():
            # Check if password is legacy format (not bcrypt)
            if not user.password_hash.startswith("$2"):
                # Can't migrate without knowing the password
                # Just mark for password change
                user.must_change_password = True
                migrated += 1
        
        if migrated > 0:
            self._save_users()
            logger.info("Marked %d users for password migration", migrated)
        
        return migrated


# Global user manager instance
_user_manager: Optional[UserManager] = None


def get_user_manager() -> UserManager:
    """Get the global UserManager instance."""
    global _user_manager
    if _user_manager is None:
        _user_manager = UserManager()
    return _user_manager
