"""HTTP constants for the fetch layer.

Centralizes all HTTP-related constants to avoid duplication across modules.
"""

# HTTP Status Code Ranges
HTTP_STATUS_OK_MIN = 200
HTTP_STATUS_OK_MAX = 300
HTTP_STATUS_NOT_MODIFIED = 304
HTTP_STATUS_BAD_REQUEST = 400
HTTP_STATUS_TOO_MANY_REQUESTS = 429
HTTP_STATUS_SERVER_ERROR_MIN = 500
HTTP_STATUS_SERVER_ERROR_MAX = 600

# Response Size Limits
DEFAULT_MAX_RESPONSE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

# Chunk size for streaming reads
DEFAULT_CHUNK_SIZE = 8192

# Maximum retry delay cap for rate limiting (seconds)
MAX_RETRY_AFTER_SECONDS = 60
