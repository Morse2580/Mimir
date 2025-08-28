"""
Cached Result Serving - Type Definitions and Contracts

Defines types for serving cached results with staleness indicators during degraded mode.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any, Protocol, List, Generic, TypeVar
from enum import Enum
from datetime import datetime

T = TypeVar('T')


class CacheStatus(Enum):
    """Status of cached data."""
    FRESH = "fresh"
    STALE = "stale"  
    EXPIRED = "expired"
    MISSING = "missing"


class DataStaleness(Enum):
    """Levels of data staleness."""
    CURRENT = "current"      # < 1 hour old
    RECENT = "recent"        # 1-6 hours old
    AGING = "aging"          # 6-24 hours old
    STALE = "stale"          # 1-7 days old
    VERY_STALE = "very_stale" # > 7 days old


@dataclass(frozen=True)
class CacheKey:
    """Key for cached data with context."""
    
    namespace: str
    identifier: str
    version: str = "v1"
    context: Optional[Dict[str, str]] = None
    
    def to_redis_key(self) -> str:
        """Convert to Redis key format."""
        base_key = f"cache:{self.namespace}:{self.identifier}:{self.version}"
        if self.context:
            context_str = "|".join(f"{k}={v}" for k, v in sorted(self.context.items()))
            return f"{base_key}#{context_str}"
        return base_key


@dataclass(frozen=True) 
class CachedResult(Generic[T]):
    """Container for cached data with metadata."""
    
    data: T
    cache_key: CacheKey
    cached_at: datetime
    expires_at: datetime
    staleness: DataStaleness
    status: CacheStatus
    hit_count: int = 0
    last_accessed: Optional[datetime] = None
    source_system: Optional[str] = None
    data_version: Optional[str] = None
    

@dataclass(frozen=True)
class StalenessWarning:
    """Warning about stale cached data."""
    
    cache_key: CacheKey
    staleness_level: DataStaleness
    age_hours: float
    last_updated: datetime
    expected_freshness_hours: float
    warning_message: str
    recommended_action: str


@dataclass(frozen=True)
class CacheConfig:
    """Configuration for cache behavior."""
    
    default_ttl_hours: int = 24
    staleness_warning_hours: int = 6
    max_stale_serve_hours: int = 168  # 7 days
    enable_stale_while_revalidate: bool = True
    background_refresh_threshold: float = 0.8  # Refresh when 80% of TTL elapsed
    compression_enabled: bool = True
    max_cache_size_mb: int = 1000


@dataclass(frozen=True)
class CacheMetrics:
    """Metrics for cache performance."""
    
    total_requests: int
    cache_hits: int
    cache_misses: int
    stale_hits: int
    expired_items: int
    background_refreshes: int
    average_response_time_ms: float
    cache_size_bytes: int
    hit_rate: float
    stale_hit_rate: float
    

class CacheStore(Protocol[T]):
    """Protocol for cache storage implementations."""
    
    async def get(self, key: CacheKey) -> Optional[CachedResult[T]]:
        """Retrieve cached item."""
        ...
        
    async def put(
        self, 
        key: CacheKey, 
        data: T, 
        ttl_hours: Optional[int] = None
    ) -> None:
        """Store item in cache."""
        ...
        
    async def delete(self, key: CacheKey) -> bool:
        """Delete cached item."""
        ...
        
    async def exists(self, key: CacheKey) -> bool:
        """Check if key exists in cache."""
        ...
        
    async def get_metrics(self) -> CacheMetrics:
        """Get cache performance metrics."""
        ...


class StalenessAnalyzer(Protocol):
    """Protocol for analyzing data staleness."""
    
    def calculate_staleness(
        self, 
        cached_at: datetime, 
        expected_freshness_hours: float
    ) -> DataStaleness:
        """Calculate staleness level."""
        ...
        
    def should_warn(
        self, 
        result: CachedResult[T], 
        config: CacheConfig
    ) -> Optional[StalenessWarning]:
        """Determine if staleness warning needed."""
        ...
        
    def can_serve_stale(
        self, 
        result: CachedResult[T], 
        config: CacheConfig
    ) -> bool:
        """Determine if stale data can still be served."""
        ...


@dataclass(frozen=True)
class CacheOperation:
    """Represents a cache operation for queueing."""
    
    operation_type: str  # "get", "put", "delete", "refresh"
    cache_key: CacheKey
    requested_at: datetime
    priority: int = 0
    context: Optional[Dict[str, Any]] = None
    

@dataclass(frozen=True)
class BackgroundRefreshRequest:
    """Request for background cache refresh."""
    
    cache_key: CacheKey
    current_data: Any
    refresh_source: str
    priority: int
    requested_at: datetime
    estimated_refresh_time_ms: int
    context: Optional[Dict[str, Any]] = None
    

class CacheFallbackStrategy(Enum):
    """Strategies for handling cache misses during degraded mode."""
    SERVE_STALE = "serve_stale"
    RETURN_EMPTY = "return_empty"  
    QUEUE_FOR_LATER = "queue_for_later"
    USE_RSS_FALLBACK = "use_rss_fallback"
    

@dataclass(frozen=True)
class DegradedCacheResponse(Generic[T]):
    """Response containing cached data with degraded mode context."""
    
    data: Optional[T]
    cache_status: CacheStatus
    staleness_warning: Optional[StalenessWarning]
    fallback_strategy_used: Optional[CacheFallbackStrategy]
    response_source: str  # "cache", "rss_fallback", "queue"
    response_time_ms: int
    degraded_mode_active: bool
    recommendations: List[str] = None
    
    def __post_init__(self):
        """Set default empty list for recommendations."""
        if self.recommendations is None:
            object.__setattr__(self, 'recommendations', [])