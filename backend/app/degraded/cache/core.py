"""
Cached Result Serving - Core Functions

Pure functions for cache management, staleness analysis, and degraded mode decisions.
"""

import json
import hashlib
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from .contracts import (
    CacheKey,
    CachedResult,
    DataStaleness,
    CacheStatus,
    StalenessWarning,
    CacheConfig,
    CacheFallbackStrategy,
    DegradedCacheResponse
)


def calculate_data_staleness(
    cached_at: datetime,
    current_time: datetime,
    expected_freshness_hours: float = 6.0
) -> DataStaleness:
    """
    Calculate staleness level based on cache age.
    
    Args:
        cached_at: When data was cached
        current_time: Current timestamp
        expected_freshness_hours: Expected data freshness window
        
    Returns:
        DataStaleness level
        
    MUST be deterministic.
    """
    if cached_at > current_time:
        # Handle clock skew - treat as current
        return DataStaleness.CURRENT
        
    age_delta = current_time - cached_at
    age_hours = age_delta.total_seconds() / 3600
    
    if age_hours < 1.0:
        return DataStaleness.CURRENT
    elif age_hours < expected_freshness_hours:
        return DataStaleness.RECENT
    elif age_hours < 24.0:
        return DataStaleness.AGING
    elif age_hours < 168.0:  # 7 days
        return DataStaleness.STALE
    else:
        return DataStaleness.VERY_STALE


def determine_cache_status(
    cached_result: Optional[CachedResult],
    current_time: datetime
) -> CacheStatus:
    """
    Determine cache status for given result.
    
    Args:
        cached_result: Cached result or None
        current_time: Current timestamp
        
    Returns:
        CacheStatus indicating data availability
        
    MUST be deterministic.
    """
    if cached_result is None:
        return CacheStatus.MISSING
        
    if current_time >= cached_result.expires_at:
        return CacheStatus.EXPIRED
        
    staleness = calculate_data_staleness(
        cached_result.cached_at,
        current_time
    )
    
    if staleness in [DataStaleness.CURRENT, DataStaleness.RECENT]:
        return CacheStatus.FRESH
    else:
        return CacheStatus.STALE


def should_warn_about_staleness(
    cached_result: CachedResult,
    config: CacheConfig,
    current_time: datetime
) -> bool:
    """
    Determine if staleness warning should be shown.
    
    Args:
        cached_result: Cached result to check
        config: Cache configuration
        current_time: Current timestamp
        
    Returns:
        True if warning should be shown
        
    MUST be deterministic.
    """
    age_delta = current_time - cached_result.cached_at
    age_hours = age_delta.total_seconds() / 3600
    
    return age_hours >= config.staleness_warning_hours


def create_staleness_warning(
    cached_result: CachedResult,
    current_time: datetime,
    expected_freshness_hours: float = 6.0
) -> StalenessWarning:
    """
    Create staleness warning for cached data.
    
    Args:
        cached_result: Cached result to warn about
        current_time: Current timestamp
        expected_freshness_hours: Expected freshness window
        
    Returns:
        StalenessWarning with details
        
    MUST be deterministic.
    """
    age_delta = current_time - cached_result.cached_at
    age_hours = age_delta.total_seconds() / 3600
    
    staleness = calculate_data_staleness(
        cached_result.cached_at,
        current_time,
        expected_freshness_hours
    )
    
    warning_messages = {
        DataStaleness.AGING: f"Data is {age_hours:.1f} hours old and may be outdated",
        DataStaleness.STALE: f"Data is {age_hours:.1f} hours old and likely outdated",
        DataStaleness.VERY_STALE: f"Data is {age_hours:.1f} hours old and very likely outdated"
    }
    
    recommendations = {
        DataStaleness.AGING: "Consider refreshing data if critical decisions depend on it",
        DataStaleness.STALE: "Strongly recommend refreshing data before making decisions",
        DataStaleness.VERY_STALE: "Data refresh required - current data may be significantly incorrect"
    }
    
    warning_msg = warning_messages.get(
        staleness,
        f"Data is {age_hours:.1f} hours old"
    )
    
    recommended_action = recommendations.get(
        staleness,
        "Monitor data freshness"
    )
    
    return StalenessWarning(
        cache_key=cached_result.cache_key,
        staleness_level=staleness,
        age_hours=age_hours,
        last_updated=cached_result.cached_at,
        expected_freshness_hours=expected_freshness_hours,
        warning_message=warning_msg,
        recommended_action=recommended_action
    )


def can_serve_stale_data(
    cached_result: CachedResult,
    config: CacheConfig,
    current_time: datetime
) -> bool:
    """
    Determine if stale data can still be served.
    
    Args:
        cached_result: Cached result to check
        config: Cache configuration
        current_time: Current timestamp
        
    Returns:
        True if stale data can be served
        
    MUST be deterministic.
    """
    age_delta = current_time - cached_result.cached_at
    age_hours = age_delta.total_seconds() / 3600
    
    return age_hours <= config.max_stale_serve_hours


def choose_fallback_strategy(
    cache_status: CacheStatus,
    degraded_mode_active: bool,
    data_critical: bool = False
) -> CacheFallbackStrategy:
    """
    Choose appropriate fallback strategy based on context.
    
    Args:
        cache_status: Current cache status
        degraded_mode_active: Whether degraded mode is active
        data_critical: Whether this is critical data
        
    Returns:
        CacheFallbackStrategy to use
        
    MUST be deterministic.
    """
    if cache_status == CacheStatus.MISSING:
        if degraded_mode_active:
            return CacheFallbackStrategy.USE_RSS_FALLBACK
        else:
            return CacheFallbackStrategy.QUEUE_FOR_LATER
            
    elif cache_status == CacheStatus.EXPIRED:
        if degraded_mode_active:
            return CacheFallbackStrategy.SERVE_STALE
        else:
            return CacheFallbackStrategy.QUEUE_FOR_LATER
            
    elif cache_status == CacheStatus.STALE:
        if data_critical and not degraded_mode_active:
            return CacheFallbackStrategy.QUEUE_FOR_LATER
        else:
            return CacheFallbackStrategy.SERVE_STALE
            
    else:  # FRESH
        return CacheFallbackStrategy.SERVE_STALE  # No fallback needed


def should_background_refresh(
    cached_result: CachedResult,
    config: CacheConfig,
    current_time: datetime
) -> bool:
    """
    Determine if background refresh should be triggered.
    
    Args:
        cached_result: Cached result to check
        config: Cache configuration  
        current_time: Current timestamp
        
    Returns:
        True if background refresh should be triggered
        
    MUST be deterministic.
    """
    if not config.enable_stale_while_revalidate:
        return False
        
    time_to_expiry = cached_result.expires_at - current_time
    total_ttl = cached_result.expires_at - cached_result.cached_at
    
    if total_ttl.total_seconds() <= 0:
        return True  # Already expired
        
    time_remaining_ratio = time_to_expiry.total_seconds() / total_ttl.total_seconds()
    
    return time_remaining_ratio <= (1.0 - config.background_refresh_threshold)


def generate_cache_recommendations(
    cache_status: CacheStatus,
    staleness_warning: Optional[StalenessWarning],
    fallback_used: Optional[CacheFallbackStrategy],
    degraded_mode_active: bool
) -> List[str]:
    """
    Generate recommendations for cache usage.
    
    Args:
        cache_status: Status of cached data
        staleness_warning: Staleness warning if any
        fallback_used: Fallback strategy used
        degraded_mode_active: Whether degraded mode is active
        
    Returns:
        List of recommendation strings
        
    MUST be deterministic.
    """
    recommendations = []
    
    if cache_status == CacheStatus.MISSING:
        if degraded_mode_active:
            recommendations.append(
                "No cached data available - using RSS fallback data which may have limited coverage"
            )
        else:
            recommendations.append(
                "No cached data available - operation queued for when services recover"
            )
            
    elif cache_status == CacheStatus.EXPIRED:
        recommendations.append(
            "Cached data has expired - serving stale data as fallback"
        )
        if not degraded_mode_active:
            recommendations.append(
                "Consider waiting for service recovery for fresh data"
            )
            
    elif cache_status == CacheStatus.STALE:
        if staleness_warning:
            if staleness_warning.staleness_level == DataStaleness.VERY_STALE:
                recommendations.append(
                    "Data is very stale - validate any decisions based on this information"
                )
            elif staleness_warning.staleness_level == DataStaleness.STALE:
                recommendations.append(
                    "Data staleness detected - verify currency before making critical decisions"
                )
                
    if fallback_used == CacheFallbackStrategy.USE_RSS_FALLBACK:
        recommendations.append(
            "RSS fallback data may have different coverage than normal operations"
        )
        
    if degraded_mode_active:
        recommendations.append(
            "System is in degraded mode - data freshness and coverage may be limited"
        )
        
    return recommendations


def calculate_response_score(
    cache_status: CacheStatus,
    staleness: Optional[DataStaleness],
    degraded_mode_active: bool
) -> float:
    """
    Calculate quality score for cached response (0.0-1.0).
    
    Args:
        cache_status: Status of cached data
        staleness: Data staleness level if available
        degraded_mode_active: Whether degraded mode is active
        
    Returns:
        Quality score from 0.0 (poor) to 1.0 (excellent)
        
    MUST be deterministic.
    """
    if cache_status == CacheStatus.MISSING:
        return 0.1 if degraded_mode_active else 0.0
        
    if cache_status == CacheStatus.FRESH:
        return 1.0
        
    if cache_status == CacheStatus.EXPIRED:
        base_score = 0.3
    elif cache_status == CacheStatus.STALE:
        base_score = 0.6
    else:
        base_score = 0.5
        
    # Adjust based on staleness
    if staleness:
        staleness_multipliers = {
            DataStaleness.CURRENT: 1.0,
            DataStaleness.RECENT: 0.9,
            DataStaleness.AGING: 0.7,
            DataStaleness.STALE: 0.5,
            DataStaleness.VERY_STALE: 0.2
        }
        staleness_mult = staleness_multipliers.get(staleness, 0.5)
        base_score *= staleness_mult
        
    # Penalty for degraded mode
    if degraded_mode_active:
        base_score *= 0.8
        
    return min(1.0, max(0.0, base_score))


def serialize_cache_data(data: Any) -> bytes:
    """
    Serialize data for cache storage.
    
    Args:
        data: Data to serialize
        
    Returns:
        Serialized bytes
        
    MUST be deterministic.
    """
    try:
        json_str = json.dumps(data, sort_keys=True, separators=(',', ':'))
        return json_str.encode('utf-8')
    except (TypeError, ValueError) as e:
        raise ValueError(f"Cannot serialize data for caching: {str(e)}")


def deserialize_cache_data(data: bytes) -> Any:
    """
    Deserialize data from cache storage.
    
    Args:
        data: Serialized bytes
        
    Returns:
        Deserialized data
        
    MUST be deterministic.
    """
    try:
        json_str = data.decode('utf-8')
        return json.loads(json_str)
    except (ValueError, UnicodeDecodeError) as e:
        raise ValueError(f"Cannot deserialize cached data: {str(e)}")


def generate_cache_version_hash(data: Any) -> str:
    """
    Generate version hash for cached data to detect changes.
    
    Args:
        data: Data to hash
        
    Returns:
        SHA-256 hash string
        
    MUST be deterministic.
    """
    try:
        serialized = serialize_cache_data(data)
        return hashlib.sha256(serialized).hexdigest()[:16]  # First 16 chars
    except ValueError:
        # Fallback for non-serializable data
        return hashlib.sha256(str(data).encode('utf-8')).hexdigest()[:16]


def build_degraded_response(
    data: Any,
    cache_status: CacheStatus,
    staleness_warning: Optional[StalenessWarning],
    fallback_strategy: Optional[CacheFallbackStrategy],
    response_source: str,
    response_time_ms: int,
    degraded_mode_active: bool
) -> DegradedCacheResponse:
    """
    Build comprehensive degraded cache response.
    
    Args:
        data: Response data (may be None)
        cache_status: Status of cached data
        staleness_warning: Staleness warning if applicable
        fallback_strategy: Fallback strategy used
        response_source: Source of response data
        response_time_ms: Response time in milliseconds
        degraded_mode_active: Whether degraded mode is active
        
    Returns:
        DegradedCacheResponse with complete context
        
    MUST be deterministic.
    """
    staleness = staleness_warning.staleness_level if staleness_warning else None
    
    recommendations = generate_cache_recommendations(
        cache_status,
        staleness_warning,
        fallback_strategy,
        degraded_mode_active
    )
    
    return DegradedCacheResponse(
        data=data,
        cache_status=cache_status,
        staleness_warning=staleness_warning,
        fallback_strategy_used=fallback_strategy,
        response_source=response_source,
        response_time_ms=response_time_ms,
        degraded_mode_active=degraded_mode_active,
        recommendations=recommendations
    )