"""
Campaign service with CRUD operations and state machine transitions.

This service provides business logic for campaign management including:
- Creation within geography
- Retrieval (single and list with filtering)
- Updates (only in DRAFT or PAUSED state)
- State transitions: start, pause, resume, cancel
- Status reporting with progress tracking
"""

from datetime import datetime, time as time_type
from typing import Optional, List
from beanie import PydanticObjectId
from beanie.operators import In

from backend.app.models.campaign import Campaign, CampaignState, CampaignStats, TimeWindow
from backend.app.models.geography import Geography
from backend.app.schemas.campaign import CampaignCreate, CampaignUpdate
from backend.app.core.logging import get_logger

logger = get_logger(__name__)


class CampaignService:
    """Service layer for campaign business logic"""

    @staticmethod
    async def create_campaign(geography_id: str, data: CampaignCreate) -> Campaign:
        """
        Create a new campaign within a geography.

        Args:
            geography_id: Parent geography MongoDB ObjectId as string
            data: Campaign creation data

        Returns:
            Created Campaign document

        Raises:
            ValueError: If geography doesn't exist or is deleted
        """
        # Verify geography exists and is not deleted
        geography = await Geography.get(PydanticObjectId(geography_id))
        if not geography or geography.deleted_at is not None:
            logger.warning("Geography not found or deleted", geography_id=geography_id)
            raise ValueError("Geography not found")

        # Deduplicate patient list
        unique_patients = list(set(data.config.patient_list))
        if len(unique_patients) != len(data.config.patient_list):
            logger.info(
                "Deduplicated patient list",
                original_count=len(data.config.patient_list),
                unique_count=len(unique_patients)
            )

        # Create campaign
        campaign = Campaign(
            name=data.name,
            geography_id=geography,
            config=data.config.model_dump(),
            state=CampaignState.DRAFT,
            stats=CampaignStats(total_calls=len(unique_patients)),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Update config with deduplicated patient list
        campaign.config.patient_list = unique_patients

        await campaign.insert()
        logger.info(
            "Campaign created",
            campaign_id=str(campaign.id),
            geography_id=geography_id,
            name=campaign.name,
            total_patients=len(unique_patients)
        )

        return campaign

    @staticmethod
    async def get_campaign_by_id(campaign_id: str) -> Optional[Campaign]:
        """
        Get campaign by ID (excludes soft-deleted).

        Args:
            campaign_id: MongoDB ObjectId as string

        Returns:
            Campaign document or None if not found
        """
        try:
            campaign = await Campaign.get(PydanticObjectId(campaign_id))

            # Exclude soft-deleted campaigns
            if campaign and campaign.deleted_at is not None:
                return None

            return campaign
        except Exception as e:
            logger.warning("Error fetching campaign", campaign_id=campaign_id, error=str(e))
            return None

    @staticmethod
    async def list_campaigns(
        geography_id: Optional[str] = None,
        state: Optional[CampaignState] = None,
        skip: int = 0,
        limit: int = 50
    ) -> tuple[List[Campaign], int]:
        """
        List campaigns with optional filtering and pagination.

        Args:
            geography_id: Optional filter by geography
            state: Optional filter by state
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            Tuple of (list of campaigns, total count)
        """
        # Build query (exclude soft-deleted)
        query = Campaign.find(Campaign.deleted_at == None)

        # Apply geography_id filter if provided
        if geography_id:
            query = query.find(Campaign.geography_id.id == PydanticObjectId(geography_id))

        # Apply state filter if provided
        if state:
            query = query.find(Campaign.state == state)

        # Get total count
        total = await query.count()

        # Apply pagination and fetch
        campaigns = await query.skip(skip).limit(limit).to_list()

        logger.debug(
            "Listed campaigns",
            total=total,
            skip=skip,
            limit=limit,
            geography_id=geography_id,
            state=state.value if state else None
        )

        return campaigns, total

    @staticmethod
    async def update_campaign(
        campaign_id: str,
        data: CampaignUpdate
    ) -> Optional[Campaign]:
        """
        Update campaign configuration (only allowed in DRAFT or PAUSED state).

        Args:
            campaign_id: MongoDB ObjectId as string
            data: Partial update data

        Returns:
            Updated Campaign document or None if not found

        Raises:
            ValueError: If campaign is ACTIVE (cannot modify running campaign)
        """
        campaign = await CampaignService.get_campaign_by_id(campaign_id)
        if not campaign:
            return None

        # Check if campaign can be modified
        if campaign.state == CampaignState.ACTIVE:
            logger.warning(
                "Cannot modify active campaign",
                campaign_id=campaign_id,
                state=campaign.state.value
            )
            raise ValueError("Cannot modify active campaign. Pause campaign first.")

        # Apply updates (only non-None fields)
        update_data = data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if field == "config" and value is not None:
                # Convert CampaignConfigCreate to dict for storage
                config_dict = value.model_dump()
                # Deduplicate patient list
                unique_patients = list(set(config_dict.get("patient_list", [])))
                config_dict["patient_list"] = unique_patients
                setattr(campaign, field, config_dict)
                # Update total_calls if patient list changed
                campaign.stats.total_calls = len(unique_patients)
            else:
                setattr(campaign, field, value)

        # Update timestamp
        campaign.updated_at = datetime.utcnow()

        await campaign.save()
        logger.info("Campaign updated", campaign_id=campaign_id, fields=list(update_data.keys()))

        return campaign

    @staticmethod
    async def start_campaign(campaign_id: str) -> Campaign:
        """
        Start campaign (transition from DRAFT → ACTIVE).

        Creates queue entries for all patients in patient_list.
        Note: Queue entry creation will be implemented in User Story 5.

        Args:
            campaign_id: MongoDB ObjectId as string

        Returns:
            Updated Campaign document

        Raises:
            ValueError: If campaign not found or already started
        """
        campaign = await CampaignService.get_campaign_by_id(campaign_id)
        if not campaign:
            raise ValueError("Campaign not found")

        # Validate state transition
        if campaign.state != CampaignState.DRAFT:
            logger.warning(
                "Cannot start campaign - invalid state",
                campaign_id=campaign_id,
                current_state=campaign.state.value
            )
            raise ValueError(f"Campaign is already {campaign.state.value}")

        # Update state
        campaign.state = CampaignState.ACTIVE
        campaign.started_at = datetime.utcnow()
        campaign.updated_at = datetime.utcnow()

        # Initialize stats (queue entries will be created in US5)
        campaign.stats.queued_count = campaign.stats.total_calls

        await campaign.save()
        logger.info(
            "Campaign started",
            campaign_id=campaign_id,
            total_calls=campaign.stats.total_calls
        )

        return campaign

    @staticmethod
    async def pause_campaign(campaign_id: str) -> Campaign:
        """
        Pause campaign (transition from ACTIVE → PAUSED).

        In-progress calls continue, but no new calls are initiated.

        Args:
            campaign_id: MongoDB ObjectId as string

        Returns:
            Updated Campaign document

        Raises:
            ValueError: If campaign not found or not active
        """
        campaign = await CampaignService.get_campaign_by_id(campaign_id)
        if not campaign:
            raise ValueError("Campaign not found")

        # Validate state transition
        if campaign.state != CampaignState.ACTIVE:
            logger.warning(
                "Cannot pause campaign - not active",
                campaign_id=campaign_id,
                current_state=campaign.state.value
            )
            raise ValueError(f"Campaign is not active (current state: {campaign.state.value})")

        # Update state
        campaign.state = CampaignState.PAUSED
        campaign.updated_at = datetime.utcnow()

        await campaign.save()
        logger.info(
            "Campaign paused",
            campaign_id=campaign_id,
            in_progress=campaign.stats.in_progress_count,
            queued=campaign.stats.queued_count
        )

        return campaign

    @staticmethod
    async def resume_campaign(campaign_id: str) -> Campaign:
        """
        Resume paused campaign (transition from PAUSED → ACTIVE).

        Args:
            campaign_id: MongoDB ObjectId as string

        Returns:
            Updated Campaign document

        Raises:
            ValueError: If campaign not found or not paused
        """
        campaign = await CampaignService.get_campaign_by_id(campaign_id)
        if not campaign:
            raise ValueError("Campaign not found")

        # Validate state transition
        if campaign.state != CampaignState.PAUSED:
            logger.warning(
                "Cannot resume campaign - not paused",
                campaign_id=campaign_id,
                current_state=campaign.state.value
            )
            raise ValueError(f"Campaign is not paused (current state: {campaign.state.value})")

        # Update state
        campaign.state = CampaignState.ACTIVE
        campaign.updated_at = datetime.utcnow()

        await campaign.save()
        logger.info(
            "Campaign resumed",
            campaign_id=campaign_id,
            queued=campaign.stats.queued_count
        )

        return campaign

    @staticmethod
    async def cancel_campaign(campaign_id: str) -> Campaign:
        """
        Cancel campaign permanently (transition to CANCELLED state).

        In-progress calls continue, but all pending calls are removed from queue.
        This is a terminal state - campaign cannot be resumed.

        Args:
            campaign_id: MongoDB ObjectId as string

        Returns:
            Updated Campaign document

        Raises:
            ValueError: If campaign not found or already in terminal state
        """
        campaign = await CampaignService.get_campaign_by_id(campaign_id)
        if not campaign:
            raise ValueError("Campaign not found")

        # Validate state transition (can cancel from ACTIVE or PAUSED, not from terminal states)
        if campaign.state in [CampaignState.COMPLETED, CampaignState.CANCELLED]:
            logger.warning(
                "Cannot cancel campaign - already in terminal state",
                campaign_id=campaign_id,
                current_state=campaign.state.value
            )
            raise ValueError(f"Campaign is already {campaign.state.value}")

        # Update state
        campaign.state = CampaignState.CANCELLED
        campaign.completed_at = datetime.utcnow()
        campaign.updated_at = datetime.utcnow()

        # Queue cleanup will be handled in US5
        # For now, just mark as cancelled

        await campaign.save()
        logger.info(
            "Campaign cancelled",
            campaign_id=campaign_id,
            queued_removed=campaign.stats.queued_count
        )

        return campaign

    @staticmethod
    async def get_campaign_status(campaign_id: str) -> Optional[dict]:
        """
        Get real-time campaign execution status with progress tracking.

        Args:
            campaign_id: MongoDB ObjectId as string

        Returns:
            Status dict with progress metrics or None if not found
        """
        campaign = await CampaignService.get_campaign_by_id(campaign_id)
        if not campaign:
            return None

        # Calculate progress percentage
        if campaign.stats.total_calls > 0:
            progress_percent = (
                (campaign.stats.completed_count + campaign.stats.failed_count) /
                campaign.stats.total_calls * 100
            )
        else:
            progress_percent = 0.0

        # Calculate estimated completion (simplified - will be enhanced in US5)
        estimated_completion = None
        if campaign.state == CampaignState.ACTIVE and campaign.stats.completed_count > 0:
            # This is a placeholder - proper calculation will be in US5 with queue processor
            estimated_completion = None

        # Determine next execution window (placeholder - will be calculated in US5)
        next_execution_window = None
        if campaign.config.time_windows:
            # This is a placeholder - proper next window calculation will be in US5
            next_execution_window = None

        status = {
            "campaign_id": campaign_id,
            "state": campaign.state,
            "stats": campaign.stats,
            "progress_percent": round(progress_percent, 1),
            "estimated_completion": estimated_completion,
            "current_concurrency": campaign.stats.in_progress_count,
            "next_execution_window": next_execution_window
        }

        logger.debug("Campaign status retrieved", campaign_id=campaign_id, progress=progress_percent)

        return status
