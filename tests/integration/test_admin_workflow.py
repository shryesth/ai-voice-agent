"""
Integration tests for complete admin management workflow.

Tests end-to-end scenarios:
- Create multiple admins, verify login, delete one, verify deleted cannot login
- Bootstrap + create + delete workflow
- Admin lifecycle from creation to deletion
"""

import pytest
from httpx import AsyncClient
from fastapi import status

from backend.app.models.user import User, UserRole


@pytest.mark.asyncio
@pytest.mark.integration
class TestAdminWorkflow:
    """Integration tests for complete admin management workflow."""

    async def test_complete_admin_lifecycle(
        self,
        async_client: AsyncClient,
        auth_headers,
        test_db
    ):
        """
        Test complete admin lifecycle: create → login → delete → verify deletion.

        Workflow:
        1. Admin A creates Admin B
        2. Admin B logs in successfully
        3. Admin A deletes Admin B
        4. Admin B cannot login (account inactive)
        """
        # Step 1: Create second admin
        create_response = await async_client.post(
            "/api/v1/auth/admin",
            headers=auth_headers,
            json={
                "email": "adminb@example.com",
                "password": "AdminB123!"
            }
        )

        assert create_response.status_code == status.HTTP_201_CREATED
        admin_b_data = create_response.json()
        admin_b_id = admin_b_data["id"]

        # Step 2: Admin B logs in successfully
        login_response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": "adminb@example.com",
                "password": "AdminB123!"
            }
        )

        assert login_response.status_code == status.HTTP_200_OK
        login_data = login_response.json()
        assert "access_token" in login_data
        assert login_data["user"]["email"] == "adminb@example.com"
        assert login_data["user"]["role"] == "admin"

        # Step 3: Admin A deletes Admin B
        delete_response = await async_client.delete(
            f"/api/v1/auth/admin/{admin_b_id}",
            headers=auth_headers
        )

        assert delete_response.status_code == status.HTTP_204_NO_CONTENT

        # Step 4: Admin B cannot login (account inactive)
        failed_login_response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": "adminb@example.com",
                "password": "AdminB123!"
            }
        )

        assert failed_login_response.status_code == status.HTTP_401_UNAUTHORIZED

        # Step 5: Verify soft delete (is_active=False in database)
        deleted_admin = await User.get(admin_b_id)
        assert deleted_admin is not None, "User should still exist in database"
        assert deleted_admin.is_active is False, "User should be marked inactive"

    async def test_create_multiple_admins_and_delete_one(
        self,
        async_client: AsyncClient,
        auth_headers,
        test_db
    ):
        """
        Test creating multiple admins and deleting one.

        Workflow:
        1. Create Admin B and Admin C
        2. All three admins can login
        3. Delete Admin B
        4. Admin A and Admin C can still login
        5. Admin B cannot login
        """
        # Step 1: Create Admin B
        create_b_response = await async_client.post(
            "/api/v1/auth/admin",
            headers=auth_headers,
            json={
                "email": "adminb@example.com",
                "password": "AdminB123!"
            }
        )
        assert create_b_response.status_code == status.HTTP_201_CREATED
        admin_b_id = create_b_response.json()["id"]

        # Create Admin C
        create_c_response = await async_client.post(
            "/api/v1/auth/admin",
            headers=auth_headers,
            json={
                "email": "adminc@example.com",
                "password": "AdminC123!"
            }
        )
        assert create_c_response.status_code == status.HTTP_201_CREATED

        # Step 2: All three admins can login
        for email, password in [
            ("adminb@example.com", "AdminB123!"),
            ("adminc@example.com", "AdminC123!")
        ]:
            login_response = await async_client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": password}
            )
            assert login_response.status_code == status.HTTP_200_OK

        # Step 3: Delete Admin B
        delete_response = await async_client.delete(
            f"/api/v1/auth/admin/{admin_b_id}",
            headers=auth_headers
        )
        assert delete_response.status_code == status.HTTP_204_NO_CONTENT

        # Step 4: Admin C can still login
        login_c_response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": "adminc@example.com",
                "password": "AdminC123!"
            }
        )
        assert login_c_response.status_code == status.HTTP_200_OK

        # Step 5: Admin B cannot login
        login_b_response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": "adminb@example.com",
                "password": "AdminB123!"
            }
        )
        assert login_b_response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_admin_cannot_delete_themselves(
        self,
        async_client: AsyncClient,
        test_db
    ):
        """
        Test that admin cannot delete their own account.

        Workflow:
        1. Create Admin B
        2. Admin B logs in
        3. Admin B attempts to delete themselves (should fail)
        4. Admin B can still login
        """
        # Step 1: Create Admin B using seeded admin
        from backend.app.services.auth_service import AuthService

        seeded_admin = await User.find_one(User.role == UserRole.ADMIN)
        seeded_admin_token = AuthService.create_token_for_user(seeded_admin)
        seeded_admin_headers = {"Authorization": f"Bearer {seeded_admin_token}"}

        create_response = await async_client.post(
            "/api/v1/auth/admin",
            headers=seeded_admin_headers,
            json={
                "email": "adminb@example.com",
                "password": "AdminB123!"
            }
        )
        assert create_response.status_code == status.HTTP_201_CREATED

        # Step 2: Admin B logs in
        login_response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": "adminb@example.com",
                "password": "AdminB123!"
            }
        )
        assert login_response.status_code == status.HTTP_200_OK

        admin_b_token = login_response.json()["access_token"]
        admin_b_headers = {"Authorization": f"Bearer {admin_b_token}"}

        # Get Admin B's ID from /me endpoint
        me_response = await async_client.get(
            "/api/v1/auth/me",
            headers=admin_b_headers
        )
        admin_b_id = me_response.json().get("id") or str((await User.find_one(User.email == "adminb@example.com")).id)

        # Step 3: Admin B attempts self-deletion
        delete_response = await async_client.delete(
            f"/api/v1/auth/admin/{admin_b_id}",
            headers=admin_b_headers
        )
        assert delete_response.status_code == status.HTTP_409_CONFLICT

        # Step 4: Admin B can still login
        retry_login_response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": "adminb@example.com",
                "password": "AdminB123!"
            }
        )
        assert retry_login_response.status_code == status.HTTP_200_OK

    async def test_last_admin_protection(
        self,
        async_client: AsyncClient,
        test_db
    ):
        """
        Test that the last admin cannot be deleted.

        Workflow:
        1. Ensure only one admin exists
        2. Create a second admin (Admin B)
        3. Admin B deletes the first admin
        4. Admin B attempts to delete themselves (should fail - last admin)
        """
        # Step 1: Delete all admins except one
        all_admins = await User.find(User.role == UserRole.ADMIN).to_list()
        for admin in all_admins[1:]:
            await admin.delete()

        # Ensure exactly one admin exists
        admin_count = await User.find(
            User.role == UserRole.ADMIN,
            User.is_active == True
        ).count()
        assert admin_count == 1

        first_admin = all_admins[0]
        from backend.app.services.auth_service import AuthService
        first_admin_token = AuthService.create_token_for_user(first_admin)
        first_admin_headers = {"Authorization": f"Bearer {first_admin_token}"}

        # Step 2: Create Admin B
        create_response = await async_client.post(
            "/api/v1/auth/admin",
            headers=first_admin_headers,
            json={
                "email": "lastadmin@example.com",
                "password": "LastAdmin123!"
            }
        )
        assert create_response.status_code == status.HTTP_201_CREATED
        admin_b_id = create_response.json()["id"]

        # Login as Admin B
        login_response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": "lastadmin@example.com",
                "password": "LastAdmin123!"
            }
        )
        admin_b_token = login_response.json()["access_token"]
        admin_b_headers = {"Authorization": f"Bearer {admin_b_token}"}

        # Step 3: Admin B deletes first admin
        delete_first_response = await async_client.delete(
            f"/api/v1/auth/admin/{str(first_admin.id)}",
            headers=admin_b_headers
        )
        assert delete_first_response.status_code == status.HTTP_204_NO_CONTENT

        # Verify only one active admin remains
        active_admin_count = await User.find(
            User.role == UserRole.ADMIN,
            User.is_active == True
        ).count()
        assert active_admin_count == 1

        # Step 4: Admin B attempts to delete themselves (last admin - should fail)
        delete_self_response = await async_client.delete(
            f"/api/v1/auth/admin/{admin_b_id}",
            headers=admin_b_headers
        )
        assert delete_self_response.status_code == status.HTTP_409_CONFLICT

        # Verify Admin B still exists and is active
        final_admin_count = await User.find(
            User.role == UserRole.ADMIN,
            User.is_active == True
        ).count()
        assert final_admin_count == 1

    async def test_password_strength_validation_workflow(
        self,
        async_client: AsyncClient,
        auth_headers
    ):
        """
        Test password strength validation across multiple attempts.

        Workflow:
        1. Attempt to create admin with weak password (no uppercase) - fails
        2. Attempt with weak password (no digit) - fails
        3. Attempt with strong password - succeeds
        4. New admin can login
        """
        # Step 1: Weak password - no uppercase
        response1 = await async_client.post(
            "/api/v1/auth/admin",
            headers=auth_headers,
            json={
                "email": "strongadmin@example.com",
                "password": "weakpass123!"
            }
        )
        assert response1.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        # Step 2: Weak password - no digit
        response2 = await async_client.post(
            "/api/v1/auth/admin",
            headers=auth_headers,
            json={
                "email": "strongadmin@example.com",
                "password": "WeakPassword!"
            }
        )
        assert response2.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        # Step 3: Strong password - succeeds
        response3 = await async_client.post(
            "/api/v1/auth/admin",
            headers=auth_headers,
            json={
                "email": "strongadmin@example.com",
                "password": "StrongPass123!"
            }
        )
        assert response3.status_code == status.HTTP_201_CREATED

        # Step 4: New admin can login
        login_response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": "strongadmin@example.com",
                "password": "StrongPass123!"
            }
        )
        assert login_response.status_code == status.HTTP_200_OK
