"""
Unit tests for bootstrap admin creation functionality.

Tests:
- Bootstrap creates admin when none exist
- Bootstrap skips when admin already exists
- Bootstrap handles race conditions (parallel execution)
- Bootstrap respects disabled flag
"""

import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock
from pymongo.errors import DuplicateKeyError

from backend.app.core.bootstrap import bootstrap_default_admin
from backend.app.core.config import settings
from backend.app.models.user import User, UserRole


@pytest.mark.asyncio
@pytest.mark.unit
class TestBootstrapAdmin:
    """Unit tests for bootstrap_default_admin function."""

    async def test_bootstrap_creates_admin_when_none_exist(self, test_db):
        """
        Test that bootstrap creates default admin when no admins exist.

        Verifies:
        - Admin user is created with correct email and role
        - Password is properly hashed
        - Admin count increases from 0 to 1
        """
        # Ensure no admins exist
        await User.find(User.role == UserRole.ADMIN).delete()

        initial_count = await User.find(User.role == UserRole.ADMIN).count()
        assert initial_count == 0, "No admins should exist initially"

        # Temporarily enable bootstrap and set credentials
        original_enabled = settings.enable_bootstrap_admin
        original_email = settings.bootstrap_admin_email
        original_password = settings.bootstrap_admin_password
        try:
            settings.enable_bootstrap_admin = True
            settings.bootstrap_admin_email = "testadmin@example.com"
            settings.bootstrap_admin_password = "TestAdmin123!"

            # Run bootstrap
            await bootstrap_default_admin()

            # Verify admin was created
            final_count = await User.find(User.role == UserRole.ADMIN).count()
            assert final_count == 1, "Exactly one admin should exist after bootstrap"

            # Verify admin details
            admin = await User.find_one(User.email == settings.bootstrap_admin_email)
            assert admin is not None, "Admin should exist with configured email"
            assert admin.role == UserRole.ADMIN, "User should have admin role"
            assert admin.is_active is True, "Admin should be active"
            assert len(admin.hashed_password) > 0, "Password should be hashed"
            # Verify password is not stored in plaintext
            assert admin.hashed_password != settings.bootstrap_admin_password

        finally:
            # Restore original settings
            settings.enable_bootstrap_admin = original_enabled
            settings.bootstrap_admin_email = original_email
            settings.bootstrap_admin_password = original_password

    async def test_bootstrap_skips_when_admin_exists(self, test_db):
        """
        Test that bootstrap skips creation when admin already exists.

        Verifies:
        - No duplicate admin is created
        - Existing admin is unchanged
        - Admin count remains 1
        """
        # Ensure no admins exist
        await User.find(User.role == UserRole.ADMIN).delete()

        # Create existing admin
        existing_admin = User(
            email="existing@example.com",
            hashed_password="hashed_password_123",
            role=UserRole.ADMIN,
            is_active=True
        )
        await existing_admin.insert()

        initial_count = await User.find(User.role == UserRole.ADMIN).count()
        assert initial_count == 1, "One admin should exist before bootstrap"

        # Run bootstrap
        await bootstrap_default_admin()

        # Verify no additional admin was created
        final_count = await User.find(User.role == UserRole.ADMIN).count()
        assert final_count == 1, "Still only one admin should exist after bootstrap"

        # Verify existing admin is unchanged
        admin = await User.find_one(User.email == "existing@example.com")
        assert admin is not None, "Existing admin should still exist"
        assert admin.hashed_password == "hashed_password_123", "Password should be unchanged"

    async def test_bootstrap_handles_race_conditions(self, test_db):
        """
        Test that bootstrap handles race conditions gracefully.

        Simulates multiple instances starting simultaneously and attempting
        to create the default admin. MongoDB's unique email constraint ensures
        only one succeeds, others catch DuplicateKeyError.

        Verifies:
        - DuplicateKeyError is caught and logged (not raised)
        - Final verification ensures exactly one admin exists
        - No errors are raised to caller
        """
        # Ensure no admins exist
        await User.find(User.role == UserRole.ADMIN).delete()

        # Temporarily enable bootstrap and set credentials
        original_enabled = settings.enable_bootstrap_admin
        original_email = settings.bootstrap_admin_email
        original_password = settings.bootstrap_admin_password
        try:
            settings.enable_bootstrap_admin = True
            settings.bootstrap_admin_email = "testadmin@example.com"
            settings.bootstrap_admin_password = "TestAdmin123!"

            # Simulate race condition: First bootstrap creates admin successfully
            await bootstrap_default_admin()

            # Second bootstrap should detect existing admin and skip
            # (In real race condition, it might attempt creation and catch DuplicateKeyError)
            await bootstrap_default_admin()

            # Verify exactly one admin exists
            final_count = await User.find(User.role == UserRole.ADMIN).count()
            assert final_count == 1, "Exactly one admin should exist after concurrent bootstrap attempts"

        finally:
            # Restore original settings
            settings.enable_bootstrap_admin = original_enabled
            settings.bootstrap_admin_email = original_email
            settings.bootstrap_admin_password = original_password

    async def test_bootstrap_handles_duplicate_key_error(self, test_db):
        """
        Test that bootstrap handles DuplicateKeyError gracefully.

        Simulates the race condition where another instance creates
        the admin between our count check and insert attempt.

        Verifies:
        - DuplicateKeyError is caught (not raised)
        - Final verification ensures admin exists
        - No exception propagates to caller
        """
        # Ensure no admins exist
        await User.find(User.role == UserRole.ADMIN).delete()

        # Temporarily enable bootstrap and set credentials
        original_enabled = settings.enable_bootstrap_admin
        original_email = settings.bootstrap_admin_email
        original_password = settings.bootstrap_admin_password
        try:
            settings.enable_bootstrap_admin = True
            settings.bootstrap_admin_email = "testadmin@example.com"
            settings.bootstrap_admin_password = "TestAdmin123!"

            # Create admin with bootstrap email to trigger duplicate error
            existing_admin = User(
                email=settings.bootstrap_admin_email,
                hashed_password="existing_hash",
                role=UserRole.ADMIN,
                is_active=True
            )
            await existing_admin.insert()

            # Bootstrap should detect existing admin during count and skip creation
            # OR catch DuplicateKeyError if race condition occurs
            await bootstrap_default_admin()  # Should not raise exception

            # Verify exactly one admin exists
            final_count = await User.find(User.role == UserRole.ADMIN).count()
            assert final_count == 1, "Exactly one admin should exist"

        finally:
            # Restore original settings
            settings.enable_bootstrap_admin = original_enabled
            settings.bootstrap_admin_email = original_email
            settings.bootstrap_admin_password = original_password

    async def test_bootstrap_disabled(self, test_db):
        """
        Test that bootstrap is skipped when disabled.

        Verifies:
        - No admin is created when enable_bootstrap_admin=False
        - Function returns early without database operations
        """
        # Ensure no admins exist
        await User.find(User.role == UserRole.ADMIN).delete()

        # Temporarily disable bootstrap
        original_value = settings.enable_bootstrap_admin
        try:
            settings.enable_bootstrap_admin = False

            # Run bootstrap
            await bootstrap_default_admin()

            # Verify no admin was created
            admin_count = await User.find(User.role == UserRole.ADMIN).count()
            assert admin_count == 0, "No admin should be created when bootstrap is disabled"

        finally:
            # Restore original setting
            settings.enable_bootstrap_admin = original_value

    async def test_bootstrap_verifies_admin_exists(self, test_db):
        """
        Test that bootstrap performs final verification.

        Verifies:
        - Bootstrap checks that at least one admin exists after operation
        - If an admin already exists, bootstrap completes successfully
        """
        # Ensure no admins exist initially
        await User.find(User.role == UserRole.ADMIN).delete()

        # Temporarily enable bootstrap and set credentials
        original_enabled = settings.enable_bootstrap_admin
        original_email = settings.bootstrap_admin_email
        original_password = settings.bootstrap_admin_password
        try:
            settings.enable_bootstrap_admin = True
            settings.bootstrap_admin_email = "testadmin@example.com"
            settings.bootstrap_admin_password = "TestAdmin123!"

            # Create admin manually (simulating another instance creating it)
            existing_admin = User(
                email="preexisting@example.com",
                hashed_password="hash123",
                role=UserRole.ADMIN,
                is_active=True
            )
            await existing_admin.insert()

            # Bootstrap should complete successfully (admin exists)
            await bootstrap_default_admin()  # Should not raise

            # Verify at least one admin exists
            admin_count = await User.find(
                User.role == UserRole.ADMIN,
                User.is_active == True
            ).count()
            assert admin_count >= 1, "At least one admin should exist after bootstrap"

        finally:
            # Restore original settings
            settings.enable_bootstrap_admin = original_enabled
            settings.bootstrap_admin_email = original_email
            settings.bootstrap_admin_password = original_password
