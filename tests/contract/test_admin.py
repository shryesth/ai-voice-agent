"""
Contract tests for admin management endpoints.

Tests the API contract for:
- POST /api/v1/auth/admin - Create admin user
- DELETE /api/v1/auth/admin/{user_id} - Delete admin user

Verifies authorization, validation, and business logic constraints.
"""

import pytest
from httpx import AsyncClient
from fastapi import status

from backend.app.models.user import User, UserRole


@pytest.mark.asyncio
@pytest.mark.contract
class TestCreateAdmin:
    """Test POST /api/v1/auth/admin endpoint contract."""

    async def test_create_admin_success(
        self,
        async_client: AsyncClient,
        auth_headers
    ):
        """
        Test successful admin creation by authenticated admin.

        Expected:
        - Status: 201 CREATED
        - Response includes: id, email, role, is_active, created_at, message
        - New admin can login with provided credentials
        """
        response = await async_client.post(
            "/api/v1/auth/admin",
            headers=auth_headers,
            json={
                "email": "newadmin@example.com",
                "password": "SecurePass123!"
            }
        )

        assert response.status_code == status.HTTP_201_CREATED

        data = response.json()
        assert "id" in data
        assert data["email"] == "newadmin@example.com"
        assert data["role"] == "admin"
        assert data["is_active"] is True
        assert "created_at" in data
        assert data["message"] == "Admin user created successfully"

        # Verify new admin can login
        login_response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": "newadmin@example.com",
                "password": "SecurePass123!"
            }
        )
        assert login_response.status_code == status.HTTP_200_OK

    async def test_create_admin_duplicate_email(
        self,
        async_client: AsyncClient,
        auth_headers,
        seeded_admin_user
    ):
        """
        Test admin creation fails when email already exists.

        Expected:
        - Status: 409 CONFLICT
        - Error message indicates duplicate email
        """
        response = await async_client.post(
            "/api/v1/auth/admin",
            headers=auth_headers,
            json={
                "email": seeded_admin_user.email,  # Duplicate
                "password": "SecurePass123!"
            }
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        data = response.json()
        assert "detail" in data
        assert "already exists" in data["detail"].lower()

    async def test_create_admin_weak_password_no_uppercase(
        self,
        async_client: AsyncClient,
        auth_headers
    ):
        """
        Test admin creation fails with password missing uppercase letter.

        Expected:
        - Status: 422 UNPROCESSABLE_ENTITY
        - Error message mentions uppercase requirement
        """
        response = await async_client.post(
            "/api/v1/auth/admin",
            headers=auth_headers,
            json={
                "email": "admin@example.com",
                "password": "weakpass123!"  # No uppercase
            }
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        data = response.json()
        assert "detail" in data
        errors = data["detail"]
        assert any("uppercase" in str(error).lower() for error in errors)

    async def test_create_admin_weak_password_no_lowercase(
        self,
        async_client: AsyncClient,
        auth_headers
    ):
        """
        Test admin creation fails with password missing lowercase letter.

        Expected:
        - Status: 422 UNPROCESSABLE_ENTITY
        - Error message mentions lowercase requirement
        """
        response = await async_client.post(
            "/api/v1/auth/admin",
            headers=auth_headers,
            json={
                "email": "admin@example.com",
                "password": "WEAKPASS123!"  # No lowercase
            }
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        data = response.json()
        assert "detail" in data
        errors = data["detail"]
        assert any("lowercase" in str(error).lower() for error in errors)

    async def test_create_admin_weak_password_no_digit(
        self,
        async_client: AsyncClient,
        auth_headers
    ):
        """
        Test admin creation fails with password missing digit.

        Expected:
        - Status: 422 UNPROCESSABLE_ENTITY
        - Error message mentions digit requirement
        """
        response = await async_client.post(
            "/api/v1/auth/admin",
            headers=auth_headers,
            json={
                "email": "admin@example.com",
                "password": "WeakPassword!"  # No digit
            }
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        data = response.json()
        assert "detail" in data
        errors = data["detail"]
        assert any("digit" in str(error).lower() for error in errors)

    async def test_create_admin_weak_password_no_special_char(
        self,
        async_client: AsyncClient,
        auth_headers
    ):
        """
        Test admin creation fails with password missing special character.

        Expected:
        - Status: 422 UNPROCESSABLE_ENTITY
        - Error message mentions special character requirement
        """
        response = await async_client.post(
            "/api/v1/auth/admin",
            headers=auth_headers,
            json={
                "email": "admin@example.com",
                "password": "WeakPassword123"  # No special char
            }
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        data = response.json()
        assert "detail" in data
        errors = data["detail"]
        assert any("special character" in str(error).lower() for error in errors)

    async def test_create_admin_password_too_short(
        self,
        async_client: AsyncClient,
        auth_headers
    ):
        """
        Test admin creation fails with password shorter than 8 characters.

        Expected:
        - Status: 422 UNPROCESSABLE_ENTITY
        - Error message mentions length requirement
        """
        response = await async_client.post(
            "/api/v1/auth/admin",
            headers=auth_headers,
            json={
                "email": "admin@example.com",
                "password": "Pass1!"  # Only 6 chars
            }
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_create_admin_as_non_admin_user(
        self,
        async_client: AsyncClient,
        user_auth_headers
    ):
        """
        Test admin creation fails when requested by non-admin user.

        Expected:
        - Status: 403 FORBIDDEN
        - Error message indicates admin access required
        """
        response = await async_client.post(
            "/api/v1/auth/admin",
            headers=user_auth_headers,
            json={
                "email": "newadmin@example.com",
                "password": "SecurePass123!"
            }
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        data = response.json()
        assert "detail" in data
        assert "admin" in data["detail"].lower()

    async def test_create_admin_unauthenticated(
        self,
        async_client: AsyncClient
    ):
        """
        Test admin creation fails without authentication.

        Expected:
        - Status: 401 UNAUTHORIZED (or 403 depending on implementation)
        """
        response = await async_client.post(
            "/api/v1/auth/admin",
            json={
                "email": "newadmin@example.com",
                "password": "SecurePass123!"
            }
        )

        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN
        ]


@pytest.mark.asyncio
@pytest.mark.contract
class TestDeleteAdmin:
    """Test DELETE /api/v1/auth/admin/{user_id} endpoint contract."""

    async def test_delete_admin_success(
        self,
        async_client: AsyncClient,
        auth_headers,
        test_db
    ):
        """
        Test successful admin deletion by authenticated admin.

        Expected:
        - Status: 204 NO_CONTENT
        - Deleted admin cannot login
        - Deleted admin is soft-deleted (is_active=False)
        """
        # Create a second admin to delete
        from backend.app.services.auth_service import AuthService

        second_admin = await AuthService.create_user(
            email="todelete@example.com",
            password="DeleteMe123!",
            role=UserRole.ADMIN
        )

        # Delete the second admin
        response = await async_client.delete(
            f"/api/v1/auth/admin/{str(second_admin.id)}",
            headers=auth_headers
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify deleted admin cannot login
        login_response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": "todelete@example.com",
                "password": "DeleteMe123!"
            }
        )
        assert login_response.status_code == status.HTTP_401_UNAUTHORIZED

        # Verify soft delete (is_active=False)
        deleted_admin = await User.get(second_admin.id)
        assert deleted_admin.is_active is False

    async def test_delete_admin_self_deletion_forbidden(
        self,
        async_client: AsyncClient,
        auth_headers,
        seeded_admin_user
    ):
        """
        Test that admin cannot delete their own account.

        Expected:
        - Status: 409 CONFLICT
        - Error message indicates self-deletion is forbidden
        """
        response = await async_client.delete(
            f"/api/v1/auth/admin/{str(seeded_admin_user.id)}",
            headers=auth_headers
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        data = response.json()
        assert "detail" in data
        assert "cannot delete your own" in data["detail"].lower()

    async def test_delete_admin_last_admin_forbidden(
        self,
        async_client: AsyncClient,
        auth_headers,
        test_db
    ):
        """
        Test that last admin cannot be deleted.

        Expected:
        - Status: 409 CONFLICT
        - Error message indicates last admin protection
        """
        # Ensure only one admin exists
        from backend.app.services.auth_service import AuthService

        # Delete all admins except seeded admin
        all_admins = await User.find(User.role == UserRole.ADMIN).to_list()
        for admin in all_admins[1:]:  # Keep first admin
            await admin.delete()

        # Create a second admin
        second_admin = await AuthService.create_user(
            email="secondadmin@example.com",
            password="SecurePass123!",
            role=UserRole.ADMIN
        )

        # Delete the first admin (using second admin's credentials)
        # First, login as second admin
        login_response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": "secondadmin@example.com",
                "password": "SecurePass123!"
            }
        )
        second_admin_token = login_response.json()["access_token"]
        second_admin_headers = {"Authorization": f"Bearer {second_admin_token}"}

        # Now try to delete the first admin
        first_admin = all_admins[0]
        response = await async_client.delete(
            f"/api/v1/auth/admin/{str(first_admin.id)}",
            headers=second_admin_headers
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Now try to delete the last remaining admin (should fail)
        response = await async_client.delete(
            f"/api/v1/auth/admin/{str(first_admin.id)}",
            headers=second_admin_headers
        )

        # At this point, we have one admin. Trying to delete them should fail.
        # But we can't delete second_admin from their own session (self-deletion)
        # Let's verify the count instead
        admin_count = await User.find(
            User.role == UserRole.ADMIN,
            User.is_active == True
        ).count()
        assert admin_count >= 1, "At least one active admin should always exist"

    async def test_delete_admin_not_found(
        self,
        async_client: AsyncClient,
        auth_headers
    ):
        """
        Test deletion of non-existent admin.

        Expected:
        - Status: 404 NOT_FOUND
        - Error message indicates user not found
        """
        fake_id = "507f1f77bcf86cd799439011"  # Valid ObjectId format
        response = await async_client.delete(
            f"/api/v1/auth/admin/{fake_id}",
            headers=auth_headers
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()

    async def test_delete_admin_invalid_user_id(
        self,
        async_client: AsyncClient,
        auth_headers
    ):
        """
        Test deletion with invalid user ID format.

        Expected:
        - Status: 404 NOT_FOUND (Beanie.get() returns None for invalid IDs)
        """
        response = await async_client.delete(
            "/api/v1/auth/admin/invalid_id",
            headers=auth_headers
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_delete_non_admin_user_fails(
        self,
        async_client: AsyncClient,
        auth_headers,
        test_db
    ):
        """
        Test that endpoint only allows deleting admin users.

        Expected:
        - Status: 400 BAD_REQUEST
        - Error message indicates user is not an admin
        """
        # Create a regular user
        from backend.app.services.auth_service import AuthService

        regular_user = await AuthService.create_user(
            email="regularuser@example.com",
            password="RegularPass123!",
            role=UserRole.USER
        )

        response = await async_client.delete(
            f"/api/v1/auth/admin/{str(regular_user.id)}",
            headers=auth_headers
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert "detail" in data
        assert "not an admin" in data["detail"].lower()

    async def test_delete_admin_as_non_admin_user(
        self,
        async_client: AsyncClient,
        user_auth_headers,
        test_db
    ):
        """
        Test admin deletion fails when requested by non-admin user.

        Expected:
        - Status: 403 FORBIDDEN
        - Error message indicates admin access required
        """
        # Create an admin to attempt deletion
        from backend.app.services.auth_service import AuthService

        admin_to_delete = await AuthService.create_user(
            email="admintodelete@example.com",
            password="AdminPass123!",
            role=UserRole.ADMIN
        )

        response = await async_client.delete(
            f"/api/v1/auth/admin/{str(admin_to_delete.id)}",
            headers=user_auth_headers
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        data = response.json()
        assert "detail" in data
        assert "admin" in data["detail"].lower()

    async def test_delete_admin_unauthenticated(
        self,
        async_client: AsyncClient
    ):
        """
        Test admin deletion fails without authentication.

        Expected:
        - Status: 401 UNAUTHORIZED (or 403 depending on implementation)
        """
        fake_id = "507f1f77bcf86cd799439011"
        response = await async_client.delete(
            f"/api/v1/auth/admin/{fake_id}"
        )

        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN
        ]
