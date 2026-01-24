#!/usr/bin/env python3
"""
Queue Database Initialization

Creates MongoDB collections and indexes for the managed queue system.

Usage:
    python -m backend.init_queue_db

Collections created:
    - managed_queues: Queue configurations
    - managed_call_entries: Call entries with state history

Indexes created:
    - managed_queues: queue_id (unique), state, domain
    - managed_call_entries: entry_id (unique), queue_id, status, scheduled_for, compound indexes
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os

# Load environment
env_file = project_root / ".env"
if env_file.exists():
    load_dotenv(env_file)


async def init_queue_database():
    """Initialize queue database collections and indexes"""
    print("=" * 60)
    print("Queue Database Initialization")
    print("=" * 60)
    print()

    # Connect to MongoDB
    mongodb_url = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    database_name = os.getenv("MONGODB_DB_NAME", "shifo-supervisor")

    print(f"MongoDB URL: {mongodb_url}")
    print(f"Database: {database_name}")
    print()

    client = AsyncIOMotorClient(mongodb_url)
    db = client[database_name]

    try:
        # Test connection
        await client.admin.command('ping')
        print("Connected to MongoDB successfully!")
        print()
    except Exception as e:
        print(f"ERROR: Failed to connect to MongoDB: {e}")
        return False

    # Create collections if they don't exist
    collections = await db.list_collection_names()

    print("Creating collections...")
    print("-" * 40)

    if "managed_queues" not in collections:
        await db.create_collection("managed_queues")
        print("  Created: managed_queues")
    else:
        print("  Exists: managed_queues")

    if "managed_call_entries" not in collections:
        await db.create_collection("managed_call_entries")
        print("  Created: managed_call_entries")
    else:
        print("  Exists: managed_call_entries")

    print()
    print("Creating indexes...")
    print("-" * 40)

    # Indexes for managed_queues
    queues_collection = db["managed_queues"]

    await queues_collection.create_index("queue_id", unique=True)
    print("  managed_queues: queue_id (unique)")

    await queues_collection.create_index("state")
    print("  managed_queues: state")

    await queues_collection.create_index("domain")
    print("  managed_queues: domain")

    await queues_collection.create_index("created_at")
    print("  managed_queues: created_at")

    # Indexes for managed_call_entries
    entries_collection = db["managed_call_entries"]

    await entries_collection.create_index("entry_id", unique=True)
    print("  managed_call_entries: entry_id (unique)")

    await entries_collection.create_index("queue_id")
    print("  managed_call_entries: queue_id")

    await entries_collection.create_index("status")
    print("  managed_call_entries: status")

    await entries_collection.create_index("phone_number")
    print("  managed_call_entries: phone_number")

    await entries_collection.create_index("scheduled_for")
    print("  managed_call_entries: scheduled_for")

    await entries_collection.create_index("call_sid")
    print("  managed_call_entries: call_sid")

    # Compound indexes for common queries
    await entries_collection.create_index([("queue_id", 1), ("status", 1)])
    print("  managed_call_entries: queue_id + status (compound)")

    await entries_collection.create_index([("queue_id", 1), ("scheduled_for", 1)])
    print("  managed_call_entries: queue_id + scheduled_for (compound)")

    await entries_collection.create_index([("status", 1), ("scheduled_for", 1)])
    print("  managed_call_entries: status + scheduled_for (compound)")

    print()
    print("=" * 60)
    print("Database initialization complete!")
    print("=" * 60)

    client.close()
    return True


def main():
    """Main entry point"""
    success = asyncio.run(init_queue_database())
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
