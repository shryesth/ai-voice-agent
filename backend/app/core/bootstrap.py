"""
Bootstrap operations for application startup.

Provides automatic creation of default admin user to ensure
the system always has at least one admin account.
"""

from datetime import datetime
from pymongo.errors import DuplicateKeyError

from backend.app.core.config import settings
from backend.app.core.logging import get_logger
from backend.app.core.security import hash_password
from backend.app.models.user import User, UserRole

logger = get_logger(__name__)


async def bootstrap_default_admin() -> None:
    """
    Bootstrap default admin user on first startup if no admins exist.

    Security Features:
    - Only creates admin if no active admins exist in database
    - Uses secure password hashing (bcrypt)
    - Handles race conditions gracefully (multiple instances starting simultaneously)
    - Logs prominent warning about changing default credentials
    - Verifies at least one admin exists after operation

    Race Condition Handling:
    When multiple instances start simultaneously in a cluster deployment:
    1. Each instance checks admin count
    2. Multiple instances may attempt to create admin
    3. MongoDB unique email constraint ensures only one succeeds
    4. Other instances catch DuplicateKeyError and continue normally
    5. Final verification ensures at least one admin exists

    Raises:
        RuntimeError: If bootstrap fails and no admin users exist
    """
    # Check if bootstrap is enabled
    if not settings.enable_bootstrap_admin:
        logger.info("Bootstrap admin creation is disabled (ENABLE_BOOTSTRAP_ADMIN=false)")
        return

    logger.info("Checking for existing admin users")

    try:
        # Count active admin users
        admin_count = await User.find(
            User.role == UserRole.ADMIN,
            User.is_active == True
        ).count()

        if admin_count > 0:
            logger.info(
                "Admin users already exist, skipping bootstrap",
                admin_count=admin_count
            )
            return

        # No admins exist - create default admin
        logger.info("No admin users found, creating default admin user")

        try:
            default_admin = User(
                email=settings.bootstrap_admin_email,
                hashed_password=hash_password(settings.bootstrap_admin_password),
                role=UserRole.ADMIN,
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )

            await default_admin.insert()

            # Log prominent security warning
            logger.warning(
                "=" * 80 + "\n" +
                "DEFAULT ADMIN USER CREATED - CHANGE PASSWORD IMMEDIATELY\n" +
                "=" * 80 + "\n" +
                f"Email: {settings.bootstrap_admin_email}\n" +
                "Password: [Set via BOOTSTRAP_ADMIN_PASSWORD environment variable]\n" +
                "=" * 80 + "\n" +
                "ACTION REQUIRED:\n" +
                "1. Login with the bootstrap credentials\n" +
                "2. Create a new admin user with a strong password\n" +
                "3. Delete or disable the default admin account\n" +
                "4. Consider disabling bootstrap (ENABLE_BOOTSTRAP_ADMIN=false) in production\n" +
                "=" * 80,
                admin_email=settings.bootstrap_admin_email,
                security_warning=True
            )

            logger.info(
                "Default admin user created successfully",
                admin_email=settings.bootstrap_admin_email,
                admin_id=str(default_admin.id)
            )

        except DuplicateKeyError:
            # Race condition: Another instance created the admin first
            # This is expected in cluster deployments and not an error
            logger.info(
                "Default admin already exists (created by another instance)",
                admin_email=settings.bootstrap_admin_email
            )

        # Final verification: Ensure at least one admin exists
        final_admin_count = await User.find(
            User.role == UserRole.ADMIN,
            User.is_active == True
        ).count()

        if final_admin_count == 0:
            raise RuntimeError(
                "Bootstrap failed: No admin users exist after bootstrap operation. "
                "Please check database connectivity and configuration."
            )

        logger.info(
            "Bootstrap verification complete",
            admin_count=final_admin_count
        )

    except Exception as e:
        # Don't catch DuplicateKeyError here - we handle it above
        if not isinstance(e, DuplicateKeyError):
            logger.error(
                "Bootstrap operation failed",
                error=str(e),
                error_type=type(e).__name__
            )
            raise
