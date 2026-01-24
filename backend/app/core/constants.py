"""
Application-wide constants.

These constants define system limits and retry behavior for queue management.
"""

# Queue Management Constants
MAX_QUEUE_RETRIES = 3
"""Maximum number of retry attempts before moving to dead letter queue"""

MAX_CONCURRENT_CALLS = 10
"""Maximum concurrent calls allowed per queue"""


# Retry Delay Constants (in seconds)
# These define the base delay before retrying a failed call based on the failure reason

RETRY_DELAY_NO_ANSWER = 300
"""Retry delay when recipient doesn't answer (5 minutes)"""

RETRY_DELAY_BUSY = 600
"""Retry delay when recipient's line is busy (10 minutes)"""

RETRY_DELAY_FAILED = 900
"""Retry delay for general call failures (15 minutes)"""

RETRY_DELAY_TIMEOUT = 300
"""Retry delay when call times out (5 minutes)"""

RETRY_DELAY_PERSON_NOT_AVAILABLE = 1800
"""Retry delay when person is not available (30 minutes)"""

RETRY_DELAY_SHORT_DURATION = 600
"""Retry delay when call duration is too short (10 minutes)"""

RETRY_DELAY_DEFAULT = 600
"""Default retry delay for unspecified failure reasons (10 minutes)"""
