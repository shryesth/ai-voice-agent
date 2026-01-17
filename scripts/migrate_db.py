#!/usr/bin/env python3
"""
Database migration script for Patient Feedback Collection API.

Handles:
- Index creation/updates
- Data migrations between schema versions
- Backfilling new fields
- Cleanup of deprecated fields

Usage:
    python scripts/migrate_db.py [--dry-run] [--version VERSION]

Options:
    --dry-run       Show what would be done without making changes
    --version       Run migrations up to specific version (default: latest)
"""

import asyncio
import argparse
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.app.core.config import settings
from backend.app.core.database import db
from backend.app.core.logging import get_logger

logger = get_logger(__name__)


class Migration:
    """Base migration class"""

    version: str = "0.0.0"
    description: str = ""

    async def up(self, dry_run: bool = False):
        """Apply migration"""
        raise NotImplementedError

    async def down(self, dry_run: bool = False):
        """Rollback migration (optional)"""
        logger.warning(f"Rollback not implemented for {self.version}")


class Migration_1_0_0(Migration):
    """Initial schema with indexes"""

    version = "1.0.0"
    description = "Create indexes for all collections"

    async def up(self, dry_run: bool = False):
        """Create all indexes"""
        from backend.app.models.user import User
        from backend.app.models.geography import Geography
        from backend.app.models.campaign import Campaign
        from backend.app.models.call_record import CallRecord
        from backend.app.models.queue_entry import QueueEntry

        logger.info(f"Running migration {self.version}: {self.description}")

        if dry_run:
            logger.info("[DRY RUN] Would create indexes for all collections")
            return

        # Indexes are created automatically by Beanie during init_beanie()
        # This migration exists for documentation purposes
        logger.info("Indexes created via Beanie Document.Settings")


class Migration_1_0_1(Migration):
    """Backfill missing campaign stats"""

    version = "1.0.1"
    description = "Backfill campaign.stats for existing campaigns"

    async def up(self, dry_run: bool = False):
        """Backfill stats"""
        from backend.app.models.campaign import Campaign, CampaignStats
        from backend.app.models.queue_entry import QueueEntry, QueueState

        logger.info(f"Running migration {self.version}: {self.description}")

        campaigns = await Campaign.find().to_list()
        logger.info(f"Found {len(campaigns)} campaigns to check")

        updated_count = 0
        for campaign in campaigns:
            # Count queue entries
            queue_entries = await QueueEntry.find(
                QueueEntry.campaign_id == str(campaign.id)
            ).to_list()

            if not queue_entries and campaign.stats.total_calls == 0:
                # No queue entries and no stats, skip
                continue

            # Calculate stats from queue entries
            total_calls = len(queue_entries)
            pending_count = sum(1 for e in queue_entries if e.state == QueueState.PENDING)
            calling_count = sum(1 for e in queue_entries if e.state == QueueState.CALLING)
            success_count = sum(1 for e in queue_entries if e.state == QueueState.SUCCESS)
            failed_count = sum(1 for e in queue_entries if e.state == QueueState.FAILED)
            retrying_count = sum(1 for e in queue_entries if e.state == QueueState.RETRYING)
            dlq_count = sum(1 for e in queue_entries if e.moved_to_dlq)

            # Update if different
            if (
                campaign.stats.total_calls != total_calls
                or campaign.stats.pending_count != pending_count
                or campaign.stats.calling_count != calling_count
                or campaign.stats.success_count != success_count
                or campaign.stats.failed_count != failed_count
            ):
                if dry_run:
                    logger.info(
                        f"[DRY RUN] Would update campaign {campaign.id} stats: "
                        f"total={total_calls}, pending={pending_count}, calling={calling_count}, "
                        f"success={success_count}, failed={failed_count}"
                    )
                else:
                    campaign.stats.total_calls = total_calls
                    campaign.stats.queued_count = pending_count + retrying_count
                    campaign.stats.in_progress_count = calling_count
                    campaign.stats.completed_count = success_count
                    campaign.stats.failed_count = failed_count + dlq_count
                    campaign.updated_at = datetime.utcnow()
                    await campaign.save()
                    logger.info(f"Updated campaign {campaign.id} stats")

                updated_count += 1

        logger.info(f"Backfilled stats for {updated_count} campaigns")


class Migration_1_0_2(Migration):
    """Add language field to existing ConversationTurn if missing"""

    version = "1.0.2"
    description = "Backfill language field in conversation turns"

    async def up(self, dry_run: bool = False):
        """Backfill language field"""
        from backend.app.models.call_record import CallRecord

        logger.info(f"Running migration {self.version}: {self.description}")

        calls = await CallRecord.find().to_list()
        logger.info(f"Found {len(calls)} call records to check")

        updated_count = 0
        for call in calls:
            needs_update = False
            for turn in call.transcript:
                if not hasattr(turn, 'language') or turn.language is None:
                    turn.language = call.language  # Use call's language
                    needs_update = True

            if needs_update:
                if dry_run:
                    logger.info(f"[DRY RUN] Would update call {call.id} conversation turns")
                else:
                    call.updated_at = datetime.utcnow()
                    await call.save()
                    logger.info(f"Updated call {call.id} conversation turns")

                updated_count += 1

        logger.info(f"Backfilled language for {updated_count} call records")


# Registry of all migrations in order
MIGRATIONS = [
    Migration_1_0_0(),
    Migration_1_0_1(),
    Migration_1_0_2(),
]


async def get_current_version() -> str:
    """Get current database schema version"""
    # For now, we'll use a simple approach: check if collections exist
    # In production, you'd store this in a migrations collection
    try:
        from backend.app.models.user import User
        user_count = await User.find().count()
        if user_count >= 0:
            return "1.0.2"  # Latest version if collections exist
    except Exception:
        return "0.0.0"  # No schema


async def run_migrations(target_version: str = None, dry_run: bool = False):
    """Run migrations up to target version"""
    logger.info("Starting database migrations")

    if dry_run:
        logger.info("[DRY RUN MODE] No changes will be made")

    # Connect to database
    logger.info("Connecting to database")
    from backend.app.models.user import User
    from backend.app.models.geography import Geography
    from backend.app.models.campaign import Campaign
    from backend.app.models.call_record import CallRecord
    from backend.app.models.queue_entry import QueueEntry

    await db.connect(document_models=[User, Geography, Campaign, CallRecord, QueueEntry])
    logger.info("Database connected")

    # Get current version
    current_version = await get_current_version()
    logger.info(f"Current schema version: {current_version}")

    # Determine target version
    if target_version is None:
        target_version = MIGRATIONS[-1].version
    logger.info(f"Target schema version: {target_version}")

    # Run migrations
    migrations_run = 0
    for migration in MIGRATIONS:
        # Skip if already applied (version comparison)
        if migration.version <= current_version:
            logger.debug(f"Skipping migration {migration.version} (already applied)")
            continue

        # Stop if we've reached target version
        if migration.version > target_version:
            logger.info(f"Stopping at target version {target_version}")
            break

        logger.info(f"Running migration {migration.version}: {migration.description}")
        await migration.up(dry_run=dry_run)
        migrations_run += 1

    if migrations_run == 0:
        logger.info("No migrations to run")
    else:
        logger.info(f"Successfully ran {migrations_run} migrations")

    # Close database
    await db.close()
    logger.info("Database connection closed")


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Run database migrations")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    parser.add_argument(
        "--version",
        type=str,
        help="Run migrations up to specific version (default: latest)"
    )

    args = parser.parse_args()

    try:
        await run_migrations(target_version=args.version, dry_run=args.dry_run)
        logger.info("Migration completed successfully")
        return 0
    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
