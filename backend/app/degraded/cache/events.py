"""
Cached Result Serving - Domain Events

Events emitted by the cache system for monitoring and observability.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any

from .contracts import DataStaleness, CacheFallbackStrategy


@dataclass(frozen=True)
class CacheHit:
    """
    Event emitted when cache request results in a hit.
    
    Used for tracking cache performance and usage patterns.
    """
    
    event_id: str
    timestamp: datetime
    cache_key: str
    hit_count: int
    data_age_hours: float
    response_time_ms: int
    context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class CacheMiss:
    """
    Event emitted when cache request results in a miss.
    
    Critical for understanding cache effectiveness and fallback usage.
    """
    
    event_id: str
    timestamp: datetime
    cache_key: str
    fallback_strategy: CacheFallbackStrategy
    degraded_mode_active: bool
    context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class StaleDataServed:
    """
    Event emitted when stale cached data is served to maintain availability.
    
    Important for tracking data quality during degraded operations.
    """
    
    event_id: str
    timestamp: datetime
    cache_key: str
    staleness_level: DataStaleness
    age_hours: float
    degraded_mode_active: bool
    served_anyway_reason: str = "degraded_mode_fallback"
    context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class StalenessWarningIssued:
    """
    Event emitted when staleness warning is issued to users.
    
    Tracks when users are warned about potentially outdated data.
    """
    
    event_id: str
    timestamp: datetime
    cache_key: str
    staleness_level: DataStaleness
    age_hours: float
    warning_message: str
    user_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class CacheRefreshTriggered:
    """
    Event emitted when background cache refresh is triggered.
    
    Used to track proactive cache maintenance and refresh patterns.
    """
    
    event_id: str
    timestamp: datetime
    cache_key: str
    refresh_reason: str  # "background_refresh", "manual", "expired"
    current_data_age_hours: float
    estimated_refresh_time_ms: int = 0
    context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class CacheRefreshCompleted:
    """
    Event emitted when cache refresh operation completes.
    
    Tracks success/failure of cache refresh operations.
    """
    
    event_id: str
    timestamp: datetime
    cache_key: str
    refresh_successful: bool
    refresh_duration_ms: int
    data_changed: bool
    error_message: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class CacheEviction:
    """
    Event emitted when cache entries are evicted.
    
    Monitors cache pressure and eviction patterns.
    """
    
    event_id: str
    timestamp: datetime
    cache_key: str
    eviction_reason: str  # "expired", "lru", "size_limit", "manual"
    data_age_hours: float
    hit_count: int
    context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class DegradedModeActivated:
    """
    Event emitted when degraded mode is activated for cache operations.
    
    Indicates the cache system has switched to fallback strategies.
    """
    
    event_id: str
    timestamp: datetime
    trigger_reason: str
    affected_cache_namespaces: list[str]
    fallback_strategies_enabled: list[CacheFallbackStrategy]
    estimated_performance_impact: float  # 0.0-1.0
    context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class DegradedModeDeactivated:
    """
    Event emitted when degraded mode is deactivated for cache operations.
    
    Indicates return to normal cache operations.
    """
    
    event_id: str
    timestamp: datetime
    degraded_duration_seconds: int
    operations_served_stale: int
    fallback_data_used: int
    cache_refresh_backlog: int
    context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class CacheHealthCheck:
    """
    Event emitted periodically with cache system health metrics.
    
    Provides aggregated cache performance and health data.
    """
    
    event_id: str
    timestamp: datetime
    total_cache_size_mb: float
    hit_rate_percentage: float
    stale_hit_rate_percentage: float
    average_response_time_ms: float
    active_keys_count: int
    expired_keys_count: int
    degraded_mode_active: bool
    background_refreshes_pending: int
    context: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Validate health check metrics."""
        if not (0 <= self.hit_rate_percentage <= 100):
            raise ValueError("Hit rate must be between 0 and 100")
        if not (0 <= self.stale_hit_rate_percentage <= 100):
            raise ValueError("Stale hit rate must be between 0 and 100")


@dataclass(frozen=True)
class FallbackDataSourceUsed:
    """
    Event emitted when fallback data source is used instead of cache.
    
    Tracks usage of RSS fallback or other alternative data sources.
    """
    
    event_id: str
    timestamp: datetime
    cache_key: str
    fallback_source: str  # "rss_fallback", "manual_input", "static_data"
    fallback_strategy: CacheFallbackStrategy
    fallback_response_time_ms: int
    data_quality_estimate: float  # 0.0-1.0
    degraded_mode_active: bool
    context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class CacheConsistencyCheck:
    """
    Event emitted when cache consistency checks are performed.
    
    Monitors data integrity and consistency across cache operations.
    """
    
    event_id: str
    timestamp: datetime
    check_type: str  # "periodic", "triggered", "manual"
    keys_checked: int
    inconsistencies_found: int
    auto_corrected: int
    manual_intervention_needed: int
    check_duration_ms: int
    context: Optional[Dict[str, Any]] = None