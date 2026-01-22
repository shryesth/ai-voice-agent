"""
Geography service with CRUD operations and soft delete support.

This service provides business logic for geography management including:
- Creation with duplicate name checking
- Retrieval (single and list with filtering)
- Updates
- Soft delete with active campaign validation
"""

from datetime import datetime
from typing import Optional, List
from beanie import PydanticObjectId
from beanie.operators import In

from backend.app.models.geography import Geography
from backend.app.models.campaign import Campaign, CampaignState
from backend.app.schemas.geography import GeographyCreate, GeographyUpdate
from backend.app.core.logging import get_logger

logger = get_logger(__name__)


class GeographyService:
    """Service layer for geography business logic"""

    @staticmethod
    async def create_geography(data: GeographyCreate) -> Geography:
        """
        Create a new geography with duplicate name checking.

        Args:
            data: Geography creation data

        Returns:
            Created Geography document

        Raises:
            ValueError: If geography with same name already exists
        """
        # Check for duplicate name (case-insensitive)
        existing = await Geography.find_one(
            Geography.name == data.name,
            Geography.deleted_at == None
        )
        if existing:
            logger.warning("Duplicate geography name", name=data.name)
            raise ValueError(f"Geography with name '{data.name}' already exists")

        # Create new geography
        geography = Geography(
            name=data.name,
            description=data.description,
            region_code=data.region_code,
            timezone=getattr(data, 'timezone', 'UTC'),
            default_language=getattr(data, 'default_language', 'en'),
            supported_languages=getattr(data, 'supported_languages', ['en']),
            clarity_config=data.clarity_config.model_dump() if data.clarity_config else None,
            retention_policy=data.retention_policy.model_dump(),
            metadata=data.metadata,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        await geography.insert()
        logger.info("Geography created", geography_id=str(geography.id), name=geography.name)

        return geography

    @staticmethod
    async def get_geography_by_id(geography_id: str) -> Optional[Geography]:
        """
        Get geography by ID (excludes soft-deleted).

        Args:
            geography_id: MongoDB ObjectId as string

        Returns:
            Geography document or None if not found
        """
        try:
            geography = await Geography.get(PydanticObjectId(geography_id))

            # Exclude soft-deleted geographies
            if geography and geography.deleted_at is not None:
                return None

            return geography
        except Exception as e:
            logger.warning("Error fetching geography", geography_id=geography_id, error=str(e))
            return None

    @staticmethod
    async def list_geographies(
        region_code: Optional[str] = None,
        skip: int = 0,
        limit: int = 50
    ) -> tuple[List[Geography], int]:
        """
        List geographies with optional filtering and pagination.

        Args:
            region_code: Optional filter by region code
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            Tuple of (list of geographies, total count)
        """
        # Build query (exclude soft-deleted)
        query = Geography.find(Geography.deleted_at == None)

        # Apply region_code filter if provided
        if region_code:
            query = query.find(Geography.region_code == region_code)

        # Get total count
        total = await query.count()

        # Apply pagination and fetch
        geographies = await query.skip(skip).limit(limit).to_list()

        logger.debug(
            "Listed geographies",
            total=total,
            skip=skip,
            limit=limit,
            region_code=region_code
        )

        return geographies, total

    @staticmethod
    async def update_geography(
        geography_id: str,
        data: GeographyUpdate
    ) -> Optional[Geography]:
        """
        Update geography with partial data.

        Args:
            geography_id: MongoDB ObjectId as string
            data: Partial update data

        Returns:
            Updated Geography document or None if not found

        Raises:
            ValueError: If updating name to an existing name
        """
        geography = await GeographyService.get_geography_by_id(geography_id)
        if not geography:
            return None

        # Check for duplicate name if name is being updated
        if data.name and data.name != geography.name:
            existing = await Geography.find_one(
                Geography.name == data.name,
                Geography.deleted_at == None
            )
            if existing:
                logger.warning("Duplicate geography name on update", name=data.name)
                raise ValueError(f"Geography with name '{data.name}' already exists")

        # Apply updates (only non-None fields)
        update_data = data.model_dump(exclude_unset=True)
        
        logger.info(f"Updating geography {geography_id} with data: {update_data}")

        for field, value in update_data.items():
            if field == "retention_policy" and value is not None:
                # value is already a dict from model_dump(), just use it directly
                setattr(geography, field, value if isinstance(value, dict) else value.model_dump())
            elif field == "clarity_config" and value is not None:
                # Handle clarity_config the same way as retention_policy
                logger.info(f"Setting clarity_config to: {value}")
                setattr(geography, field, value if isinstance(value, dict) else value.model_dump())
            else:
                setattr(geography, field, value)

        # Update timestamp
        geography.updated_at = datetime.utcnow()

        await geography.save()
        logger.info("Geography updated", geography_id=geography_id, fields=list(update_data.keys()))

        return geography

    @staticmethod
    async def delete_geography(geography_id: str) -> bool:
        """
        Soft delete geography (set deleted_at timestamp).

        Validates that geography has no active campaigns before deletion.

        Args:
            geography_id: MongoDB ObjectId as string

        Returns:
            True if deleted, False if not found

        Raises:
            ValueError: If geography has active campaigns
        """
        geography = await GeographyService.get_geography_by_id(geography_id)
        if not geography:
            return False

        # Check for active campaigns
        active_campaign = await Campaign.find_one(
            Campaign.geography_id == PydanticObjectId(geography_id),
            In(Campaign.state, [CampaignState.ACTIVE, CampaignState.PAUSED])
        )

        if active_campaign:
            logger.warning(
                "Cannot delete geography with active campaigns",
                geography_id=geography_id
            )
            raise ValueError(
                "Cannot delete geography with active campaigns. Pause or complete campaigns first."
            )

        # Soft delete
        geography.deleted_at = datetime.utcnow()
        geography.updated_at = datetime.utcnow()
        await geography.save()

        logger.info("Geography soft deleted", geography_id=geography_id)
        return True
