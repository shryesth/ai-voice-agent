"""
Setup script to:
1. Create a geography with Clarity mock server integration
2. Create a 24x7 FOREVER queue
3. Sync data from Clarity
4. Activate queue and trigger initial sync

Prerequisites:
- API server running at http://localhost:3000
- Clarity mock server running at http://localhost:8001
- MongoDB, Redis, and Celery worker running
- Admin user exists (default: admin@example.com / admin123)

Note: The Clarity API key must match the one in clarity_mock_server/main.py (VALID_API_KEY).
"""

import asyncio
import httpx
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:3000"
# Use host.docker.internal for Docker containers to access host machine
CLARITY_URL_EXTERNAL = "http://localhost:8001"  # For external access
CLARITY_URL_DOCKER = "http://host.docker.internal:8001"  # For Docker containers
# API key must match the one in clarity_mock_server/main.py (VALID_API_KEY)
CLARITY_API_KEY = "mock-api-key-12345"

# Admin credentials (default bootstrap admin)
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin123"


async def login() -> str:
    """Login and get JWT token."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/api/v1/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        response.raise_for_status()
        data = response.json()
        return data["access_token"]


async def create_geography(token: str) -> str:
    """Create a geography with Clarity config."""
    headers = {"Authorization": f"Bearer {token}"}

    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

    geography_data = {
        "name": f"Test Geography - Clarity {timestamp}",
        "description": "Test geography with Clarity mock server integration",
        "region_code": "TEST",
        "timezone": "UTC",
        "default_language": "en",
        "supported_languages": ["en", "es", "fr", "ht"],
        "clarity_config": {
            "enabled": True,
            "api_url": CLARITY_URL_DOCKER,  # Use Docker-accessible URL
            "api_key": CLARITY_API_KEY,
            "organization_id": "test-org",
            "event_type_mapping": {},
            "skip_event_types": [],
            "auto_push_results": True,
            "include_recording_url": True,
            "default_country_code": "255",  # Tanzania (matches mock data)
        },
        "retention_policy": {
            "retention_days": 365,
            "auto_purge_enabled": False,
            "compliance_notes": "Test environment - 1 year retention",
        },
    }

    async with httpx.AsyncClient() as client:
        # Create new geography
        response = await client.post(
            f"{BASE_URL}/api/v1/geographies",
            headers=headers,
            json=geography_data,
        )
        response.raise_for_status()
        geography = response.json()
        print(f"✓ Created geography: {geography['name']} (ID: {geography['id']})")
        return geography["id"]


async def create_forever_queue(token: str, geography_id: str) -> str:
    """Create a 24x7 FOREVER queue with Clarity sync."""
    headers = {"Authorization": f"Bearer {token}"}

    queue_data = {
        "name": "24x7 Forever Queue - Clarity Sync",
        "description": "Continuous queue syncing from Clarity mock server",
        "mode": "forever",  # FOREVER mode for continuous operation
        "call_type": "patient_feedback",
        "default_language": "en",
        "max_concurrent_calls": 5,
        "time_windows": [],  # Empty = 24x7 operation
        "retry_strategy": {
            "max_retries": 3,
            "exponential_backoff": True,
            "no_answer_delay": 1800,
            "busy_delay": 3600,
            "voicemail_delay": 7200,
        },
        "clarity_sync": {
            "enabled": True,
            "sync_interval_minutes": 5,  # Sync every 5 minutes
            "max_per_sync": 100,
            "event_type_filter": [],  # Pull all event types
        },
    }

    async with httpx.AsyncClient() as client:
        # Check if queue already exists
        response = await client.get(
            f"{BASE_URL}/api/v1/queues",
            headers=headers,
            params={"geography_id": geography_id},
        )
        response.raise_for_status()
        queues = response.json()

        for queue in queues.get("items", []):
            if queue["name"] == queue_data["name"]:
                print(f"✓ Queue already exists: {queue['name']} (ID: {queue['id']})")
                return queue["id"]

        # Create new queue
        response = await client.post(
            f"{BASE_URL}/api/v1/geographies/{geography_id}/queues",
            headers=headers,
            json=queue_data,
        )
        response.raise_for_status()
        queue = response.json()
        print(f"✓ Created queue: {queue['name']} (ID: {queue['id']})")
        return queue["id"]


async def activate_queue(token: str, queue_id: str):
    """Activate the queue to start processing."""
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/api/v1/{queue_id}/start",
            headers=headers,
        )
        response.raise_for_status()
        result = response.json()
        print(f"✓ Queue activated: {result['new_state']}")


async def trigger_clarity_sync(token: str, queue_id: str):
    """Manually trigger a Clarity sync."""
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/api/v1/{queue_id}/sync-clarity",
            headers=headers,
        )
        response.raise_for_status()
        result = response.json()
        print(f"✓ Clarity sync triggered: {result['synced_count']} recipients synced")
        print(f"  Task ID: {result['task_id']}")
        return result


async def get_queue_status(token: str, queue_id: str):
    """Get queue status and statistics."""
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}/api/v1/{queue_id}/status",
            headers=headers,
        )
        response.raise_for_status()
        status = response.json()

        print(f"\n📊 Queue Status:")
        print(f"  State: {status['state']}")
        print(f"  Mode: {status['mode']}")
        print(f"  Total Recipients: {status['total_recipients']}")
        print(f"  Progress: {status['progress_percent']:.1f}%")
        print(f"\n  Status Breakdown:")
        for status_name, count in status['status_counts'].items():
            print(f"    {status_name}: {count}")

        return status


async def list_recipients(token: str, queue_id: str):
    """List recipients in the queue."""
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}/api/v1/recipients/queues/{queue_id}/recipients",
            headers=headers,
            params={"limit": 10},
        )
        response.raise_for_status()
        result = response.json()

        print(f"\n📋 Recipients (showing {len(result['items'])} of {result['total']}):")
        for recipient in result['items']:
            print(f"  - {recipient['contact_name']} ({recipient['contact_phone']})")
            print(f"    Status: {recipient['status']}, Language: {recipient['language']}")
            if recipient.get('event_info'):
                print(f"    Event: {recipient['event_info'].get('event_type', 'N/A')}")


async def check_clarity_mock_server():
    """Verify Clarity mock server is running and API key is valid."""
    try:
        async with httpx.AsyncClient() as client:
            # Check health endpoint
            response = await client.get(f"{CLARITY_URL_EXTERNAL}/health")
            response.raise_for_status()
            print(f"✓ Clarity mock server is running at {CLARITY_URL_EXTERNAL}")

            # Verify API key works
            headers = {"X-API-Key": CLARITY_API_KEY}
            response = await client.get(
                f"{CLARITY_URL_EXTERNAL}/api/v1/hmis/client-visits/verification",
                headers=headers,
                params={"page": 1, "pageSize": 1}
            )
            response.raise_for_status()
            print(f"✓ Clarity API key is valid: {CLARITY_API_KEY}")
            return True
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            print(f"✗ Clarity API key is invalid!")
            print(f"  Current key: {CLARITY_API_KEY}")
            print(f"  Expected key in clarity_mock_server/main.py: mock-api-key-12345")
        else:
            print(f"✗ Clarity mock server error: {e}")
        return False
    except Exception as e:
        print(f"✗ Clarity mock server is not accessible: {e}")
        print(f"  Please start it with: python clarity_mock_server/main.py")
        return False


async def main():
    """Main setup flow."""
    print("=" * 60)
    print("🚀 Setting up Clarity-integrated 24x7 Forever Queue")
    print("=" * 60)
    print()

    # Step 0: Check Clarity mock server
    print("Step 0: Verifying Clarity mock server...")
    if not await check_clarity_mock_server():
        return
    print()

    # Step 1: Login
    print("Step 1: Logging in...")
    try:
        token = await login()
        print("✓ Logged in successfully")
    except Exception as e:
        print(f"✗ Login failed: {e}")
        import traceback
        traceback.print_exc()
        print("  Make sure the API is running and admin user exists")
        return
    print()

    # Step 2: Create geography
    print("Step 2: Creating geography with Clarity config...")
    try:
        geography_id = await create_geography(token)
    except Exception as e:
        print(f"✗ Failed to create geography: {e}")
        return
    print()

    # Step 3: Create forever queue
    print("Step 3: Creating 24x7 FOREVER queue...")
    try:
        queue_id = await create_forever_queue(token, geography_id)
    except Exception as e:
        print(f"✗ Failed to create queue: {e}")
        return
    print()

    # Step 4: Activate queue
    print("Step 4: Activating queue...")
    try:
        await activate_queue(token, queue_id)
    except Exception as e:
        print(f"✗ Failed to activate queue: {e}")
        return
    print()

    # Step 5: Trigger Clarity sync
    print("Step 5: Triggering Clarity sync...")
    try:
        sync_result = await trigger_clarity_sync(token, queue_id)
    except Exception as e:
        print(f"✗ Failed to sync from Clarity: {e}")
        import traceback
        traceback.print_exc()
        print("\nNote: Sync failed but queue is active. Celery Beat will retry automatically every 5 minutes.")
        print("You can also trigger manual sync later.")
        # Continue to show queue info
    print()

    # Wait a moment for sync to complete
    print("Waiting 3 seconds for sync to complete...")
    await asyncio.sleep(3)
    print()

    # Step 6: Check queue status
    print("Step 6: Checking queue status...")
    try:
        status = await get_queue_status(token, queue_id)
    except Exception as e:
        print(f"✗ Failed to get queue status: {e}")
        return
    print()

    # Step 7: List recipients
    print("Step 7: Listing recipients...")
    try:
        await list_recipients(token, queue_id)
    except Exception as e:
        print(f"✗ Failed to list recipients: {e}")
        return
    print()

    # Summary
    print("=" * 60)
    print("✅ Setup Complete!")
    print("=" * 60)
    print(f"Geography ID: {geography_id}")
    print(f"Queue ID: {queue_id}")
    print(f"Clarity URL (external): {CLARITY_URL_EXTERNAL}")
    print(f"Clarity URL (Docker): {CLARITY_URL_DOCKER}")
    print(f"API URL: {BASE_URL}")
    print()
    print("The queue is now active and will:")
    print("  • Run 24x7 (no time window restrictions)")
    print("  • Sync from Clarity every 5 minutes automatically")
    print("  • Process up to 5 concurrent calls")
    print("  • Retry failed calls with exponential backoff")
    print()
    print("Monitor the queue:")
    print(f"  • Queue status: GET {BASE_URL}/api/v1/{queue_id}/status")
    print(f"  • Recipients: GET {BASE_URL}/api/v1/recipients/queues/{queue_id}/recipients")
    print(f"  • Manual sync: POST {BASE_URL}/api/v1/{queue_id}/sync-clarity")
    print()


if __name__ == "__main__":
    asyncio.run(main())
