"""
Configuration Module
Loads all environment variables and provides structured configuration
"""

import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load environment variables
load_dotenv(override=True)


class OpenAIConfig(BaseSettings):
    """Base OpenAI configuration (API key shared across services)"""

    api_key: str = ""
    model: str = "gpt-4o-mini"  # Model for text completions (translation, etc.)

    model_config = SettingsConfigDict(env_prefix="OPENAI_")


class OpenAIRealtimeConfig(BaseSettings):
    """OpenAI Realtime API configuration for voice calls"""

    model: str = "gpt-realtime-mini-2025-10-06"
    voice: str = "alloy"
    temperature: float = 0.6

    model_config = SettingsConfigDict(env_prefix="OPENAI_REALTIME_")


class TwilioConfig(BaseSettings):
    """Twilio configuration"""

    account_sid: str = ""
    auth_token: str = ""
    phone_number: str | None = None

    model_config = SettingsConfigDict(env_prefix="TWILIO_")


class ServerConfig(BaseSettings):
    """Server configuration"""

    host: str = "0.0.0.0"
    port: int = 3000
    log_level: str = "INFO"
    environment: str = "development"  # ENVIRONMENT env var (replaces NODE_ENV)
    webhook_base_url: str | None = None  # e.g., https://your-domain.com or ngrok URL
    public_url: str | None = None  # Alternative name for webhook_base_url

    @field_validator("log_level", mode="before")
    @classmethod
    def uppercase_log_level(cls, v):
        """Ensure log_level is uppercase"""
        if isinstance(v, str):
            return v.upper()
        return v

    model_config = SettingsConfigDict(env_prefix="")


class CORSConfig(BaseSettings):
    """CORS configuration"""

    allowed_origins: str = ""

    @field_validator("allowed_origins")
    @classmethod
    def parse_origins(cls, v: str) -> List[str]:
        if not v:
            return []
        return [origin.strip() for origin in v.split(",") if origin.strip()]

    model_config = SettingsConfigDict(env_prefix="")


class VADConfig(BaseSettings):
    """Voice Activity Detection configuration"""

    # OpenAI Realtime VAD (recommended)
    use_openai_vad: bool = True  # Use OpenAI's server-side VAD (semantic turn detection)

    # Silero VAD (optional, legacy)
    use_silero_vad: bool = False  # Use Silero VAD (deprecated in favor of OpenAI VAD)
    silero_threshold: float = 0.01

    model_config = SettingsConfigDict(env_prefix="VAD_")


class InterruptionConfig(BaseSettings):
    """Interruption handling configuration"""

    enabled: bool = True  # Enable user interruptions
    # Strategy: "first_utterance" (interrupt on first word) or "standard" (wait for clear speech)
    strategy: str = "first_utterance"
    # Minimum audio duration (ms) to trigger interruption
    min_audio_duration_ms: int = 200

    model_config = SettingsConfigDict(env_prefix="INTERRUPTION_")


class TranscriptsConfig(BaseSettings):
    """Transcripts configuration"""

    enabled: bool = True
    dir: str = "./transcripts"

    @property
    def path(self) -> Path:
        return Path(self.dir).resolve()

    model_config = SettingsConfigDict(env_prefix="TRANSCRIPTS_")


class RecordingsConfig(BaseSettings):
    """Recordings configuration"""

    enabled: bool = False
    dir: str = "./recordings"
    format: str = "mp3"
    # Storage backend: 'local', 's3', or 'minio'
    storage_backend: str = "local"

    @property
    def path(self) -> Path:
        return Path(self.dir).resolve()

    @property
    def is_remote_storage(self) -> bool:
        """Check if using remote storage (S3 or MinIO)"""
        return self.storage_backend in ("s3", "minio")

    model_config = SettingsConfigDict(env_prefix="RECORDINGS_")


class MongoDBConfig(BaseSettings):
    """MongoDB configuration"""

    # Support both MONGODB_URL and MONGODB_URI (CapRover uses URI)
    url: str | None = None
    uri: str | None = None  # Alias for url (CapRover compatibility)

    # Support both MONGODB_DATABASE and MONGODB_DB_NAME (CapRover uses DB_NAME)
    database: str = "voice_agent"
    db_name: str | None = None  # Alias for database (CapRover compatibility)

    model_config = SettingsConfigDict(env_prefix="MONGODB_")

    @property
    def connection_url(self) -> str | None:
        """Get MongoDB connection URL (supports both url and uri env vars)"""
        return self.url or self.uri

    @property
    def database_name(self) -> str:
        """Get database name (supports both database and db_name env vars)"""
        return self.db_name or self.database


class S3Config(BaseSettings):
    """S3 storage configuration (AWS S3)"""

    # S3 endpoint URL (None for AWS S3, set for MinIO)
    # Example MinIO: http://localhost:9000
    # Example AWS S3: Leave empty or None
    endpoint_url: str | None = None

    # S3 credentials
    access_key: str | None = None
    secret_key: str | None = None

    # S3 bucket configuration
    bucket_name: str = "voice-agent-recordings"
    region: str = "us-east-1"

    model_config = SettingsConfigDict(env_prefix="S3_")


class MinIOConfig(BaseSettings):
    """MinIO storage configuration (S3-compatible)"""

    # MinIO endpoint (without protocol)
    endpoint: str = "localhost"
    port: int = 9000
    use_ssl: bool = False

    # MinIO credentials
    access_key: str | None = None
    secret_key: str | None = None

    # MinIO bucket configuration
    bucket: str = "voice-agent-recordings"
    recordings_bucket: str | None = None  # Optional separate bucket for recordings

    model_config = SettingsConfigDict(env_prefix="MINIO_")

    @property
    def endpoint_url(self) -> str:
        """Get full endpoint URL for boto3"""
        protocol = "https" if self.use_ssl else "http"
        return f"{protocol}://{self.endpoint}:{self.port}"

    @property
    def bucket_name(self) -> str:
        """Get recordings bucket name"""
        return self.recordings_bucket or self.bucket


class CallConfig(BaseSettings):
    """Call behavior configuration"""

    max_retries_per_stage: int = 2
    call_end_delay_seconds: int = 3

    model_config = SettingsConfigDict(env_prefix="CALL_")


class PreconnectConfig(BaseSettings):
    """OpenAI connection prewarmer configuration

    The prewarmer pre-establishes WebSocket connections to OpenAI's Realtime API
    before a call actually connects, reducing latency when calls start.
    """

    enabled: bool = True  # Toggle prewarmer on/off
    timeout_ms: int = 30000  # How long a pre-warmed connection remains valid (30 seconds)
    cleanup_interval_ms: int = 30000  # Background cleanup interval (30 seconds)
    max_connection_age_ms: int = 300000  # Max age for used connections before cleanup (5 minutes)

    model_config = SettingsConfigDict(env_prefix="PRECONNECT_")


class RedisConfig(BaseSettings):
    """Redis connection configuration"""

    host: str = "localhost"
    port: int = 6379
    password: str | None = None
    db: int = 0

    model_config = SettingsConfigDict(env_prefix="REDIS_")

    @property
    def url(self) -> str:
        """Build Redis URL from components"""
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


class QueueConfig(BaseSettings):
    """Call queue configuration (Celery + Redis)"""

    enabled: bool = False  # Enable/disable the call queue feature

    # Rate limiting
    rate_limit: str = "30/m"  # Default rate limit (30 calls per minute)

    # Retry configuration
    max_retries: int = 3  # Maximum retry attempts for failed calls
    retry_backoff: bool = True  # Use exponential backoff

    # Worker configuration
    worker_concurrency: int = 4  # Number of concurrent workers
    prefetch_multiplier: int = 1  # Tasks per worker at a time (1 = one at a time)

    # Managed queue configuration
    processor_interval_seconds: int = 30  # How often to process managed queues
    default_max_concurrent_calls: int = 5  # Default max concurrent calls per queue
    min_call_duration_seconds: int = 30  # Calls shorter than this are considered failures

    model_config = SettingsConfigDict(env_prefix="QUEUE_")


class VoiceConfig(BaseSettings):
    """Language-specific voice configuration"""

    en: str = "alloy"
    es: str = "shimmer"
    fr: str = "coral"
    ht: str = "alloy"

    model_config = SettingsConfigDict(env_prefix="VOICE_")


class HealthConfig(BaseSettings):
    """Health check configuration"""

    cache_ttl_seconds: float = 5.0  # Cache health status duration
    startup_timeout_seconds: float = 60.0  # Max wait for all services during startup validation
    per_service_timeout_seconds: float = 30.0  # Max wait per service during startup validation

    model_config = SettingsConfigDict(env_prefix="HEALTH_")


class Config:
    """Main configuration object"""

    def __init__(self):
        self.openai = OpenAIConfig()
        self.openai_realtime = OpenAIRealtimeConfig()
        self.twilio = TwilioConfig()
        self.server = ServerConfig()
        self.cors = CORSConfig()
        self.vad = VADConfig()
        self.interruption = InterruptionConfig()
        self.transcripts = TranscriptsConfig()
        self.recordings = RecordingsConfig()
        self.mongodb = MongoDBConfig()
        self.s3 = S3Config()
        self.minio = MinIOConfig()
        self.call = CallConfig()
        self.preconnect = PreconnectConfig()
        self.redis = RedisConfig()
        self.queue = QueueConfig()
        self.voice = VoiceConfig()
        self.health = HealthConfig()

        # Create directories only for local storage when enabled
        if self.recordings.enabled and self.recordings.storage_backend == "local":
            self.recordings.path.mkdir(parents=True, exist_ok=True)

    @property
    def is_production(self) -> bool:
        return self.server.environment == "production"

    @property
    def mongodb_url(self) -> str | None:
        """Get MongoDB URL (supports both MONGODB_URL and MONGODB_URI)"""
        return self.mongodb.connection_url

    @property
    def mongodb_database(self) -> str:
        """Get MongoDB database name (supports both MONGODB_DATABASE and MONGODB_DB_NAME)"""
        return self.mongodb.database_name

    @property
    def queue_redis_url(self) -> str:
        """Get Redis URL for queue (built from REDIS_* components)"""
        return self.redis.url

    @property
    def max_retries_per_stage(self) -> int:
        return self.call.max_retries_per_stage

    @property
    def call_end_delay_seconds(self) -> int:
        return self.call.call_end_delay_seconds

    @property
    def voice_en(self) -> str:
        return self.voice.en

    @property
    def voice_es(self) -> str:
        return self.voice.es

    @property
    def voice_fr(self) -> str:
        return self.voice.fr

    @property
    def voice_ht(self) -> str:
        return self.voice.ht

    @property
    def public_url(self) -> str | None:
        return self.server.public_url or self.server.webhook_base_url


# Global config instance
config = Config()
