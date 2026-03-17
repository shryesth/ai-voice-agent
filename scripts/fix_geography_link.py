"""
Fix geography_id in call_queues collection and add nexus_config to geography.

Updates the geography_id to be a proper ObjectId reference and adds Nexus configuration.
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment from config/.env.local
env_path = Path(__file__).parent.parent / "config" / ".env.local"
load_dotenv(env_path)


async def fix_geography():
    """Fix geography_id in call_queues and add nexus_config to geography."""
    # Connect to MongoDB
    mongo_uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
    print(f"Connecting to MongoDB...")
    client = AsyncIOMotorClient(mongo_uri)
    
    # List databases to find the correct one
    db_list = await client.list_database_names()
    print(f"Available databases: {db_list}")
    
    # Try common database names
    for db_name in ["voice_agent", "ai_voice_agent", "test"]:
        if db_name in db_list:
            print(f"Using database: {db_name}")
            db = client[db_name]
            break
    else:
        db = client["voice_agent"]  # Default
        print(f"Using default database: voice_agent")
    
    # Update the geography with nexus_config
    geography_id = "6970018ce0be6bf822c23d35"
    
    nexus_config = {
        "enabled": True,
        "api_url": "http://localhost:8002/api/v1/hmis",
        "api_key": "mock-api-key-12345",
        "organization_id": "test-org",
        "event_type_mapping": {},
        "skip_event_types": [],
        "auto_push_results": True,
        "include_recording_url": True,
        "default_country_code": "509"
    }
    
    result = await db.geographies.update_one(
        {"_id": ObjectId(geography_id)},
        {"$set": {"nexus_config": nexus_config}}
    )
    
    print(f"Updated {result.modified_count} geography document(s)")
    
    # Verify the update
    geography = await db.geographies.find_one({"_id": ObjectId(geography_id)})
    if not geography:
        print(f"Geography {geography_id} not found!")
        # List all geographies
        geographies = await db.geographies.find().to_list(length=10)
        print(f"Found {len(geographies)} geographies:")
        for g in geographies:
            print(f"  - {g.get('_id')}: {g.get('name')}")
        client.close()
        return
        
    print(f"Nexus config enabled: {geography.get('nexus_config', {}).get('enabled')}")
    print(f"Nexus API URL: {geography.get('nexus_config', {}).get('api_url')}")
    
    # Also fix the queue's geography_id if needed
    queue_id = "697001c2e0be6bf822c23d36"
    queue = await db.call_queues.find_one({"_id": ObjectId(queue_id)})
    
    if queue:
        current_geo_id = queue.get('geography_id')
        print(f"\nQueue geography_id type: {type(current_geo_id)}")
        
        if not isinstance(current_geo_id, ObjectId):
            result = await db.call_queues.update_one(
                {"_id": ObjectId(queue_id)},
                {"$set": {"geography_id": ObjectId(geography_id)}}
            )
            print(f"Updated queue geography_id: {result.modified_count} document(s)")
    
    client.close()


if __name__ == "__main__":
    asyncio.run(fix_geography())
