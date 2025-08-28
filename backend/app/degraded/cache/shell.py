"""
Cached Result Serving - I/O Operations

Handles cache storage, retrieval, and integration with Redis and degraded mode systems.
"""

import asyncio
import logging
import uuid
import gzip
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, TypeVar, Callable, List

try:
    import redis.asyncio as redis
except ImportError:
    redis = None

from .contracts import (
    CacheKey,
    CachedResult,
    CacheConfig,
    CacheMetrics,
    CacheStatus,
    DataStaleness,
    StalenessWarning,
    CacheFallbackStrategy,
    DegradedCacheResponse,
    BackgroundRefreshRequest
)
from .core import (
    calculate_data_staleness,
    determine_cache_status,
    should_warn_about_staleness,
    create_staleness_warning,
    can_serve_stale_data,
    choose_fallback_strategy,
    should_background_refresh,
    build_degraded_response,
    serialize_cache_data,
    deserialize_cache_data,
    generate_cache_version_hash
)
from .events import (
    CacheHit,
    CacheMiss,
    StaleDataServed,
    CacheRefreshTriggered,
    StalenessWarningIssued
)

logger = logging.getLogger(__name__)
T = TypeVar('T')


class CacheManagerError(Exception):
    """Raised when cache manager encounters errors."""
    
    def __init__(self, message: str, cache_key: Optional[CacheKey] = None, original_error: Exception = None):
        self.cache_key = cache_key
        self.original_error = original_error
        super().__init__(message)


class DegradedCacheManager:
    """
    Cache manager with degraded mode support and staleness warnings.
    
    Provides caching with awareness of degraded mode operations and intelligent
    staleness handling for continuous service during external service outages.
    """
    
    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None,
        config: Optional[CacheConfig] = None,
        event_publisher: Optional[Callable] = None,
        fallback_data_source: Optional[Callable] = None
    ):
        self.redis = redis_client
        self.config = config or CacheConfig()
        self.event_publisher = event_publisher or self._default_event_publisher
        self.fallback_data_source = fallback_data_source
        
        # Metrics tracking
        self._metrics = {
            'total_requests': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'stale_hits': 0,
            'expired_items': 0,
            'background_refreshes': 0,
            'total_response_time_ms': 0
        }
    
    async def get_with_degraded_handling(
        self,
        cache_key: CacheKey,
        data_critical: bool = False,
        degraded_mode_active: bool = False,
        expected_freshness_hours: float = 6.0
    ) -> DegradedCacheResponse[Any]:
        """
        Get cached data with comprehensive degraded mode handling.
        
        Args:
            cache_key: Key for cached data
            data_critical: Whether this data is critical for operations
            degraded_mode_active: Whether system is in degraded mode
            expected_freshness_hours: Expected data freshness window
            
        Returns:
            DegradedCacheResponse with data and context
        """
        start_time = datetime.utcnow()
        self._metrics['total_requests'] += 1
        
        try:
            # Attempt to get cached data
            cached_result = await self._get_from_cache(cache_key)
            current_time = datetime.utcnow()
            
            # Determine cache status
            cache_status = determine_cache_status(cached_result, current_time)
            
            # Handle different cache scenarios
            if cache_status == CacheStatus.FRESH:
                return await self._handle_fresh_cache(
                    cached_result, cache_key, start_time, degraded_mode_active
                )
                
            elif cache_status == CacheStatus.STALE:
                return await self._handle_stale_cache(
                    cached_result, cache_key, start_time, degraded_mode_active,
                    data_critical, expected_freshness_hours
                )
                
            elif cache_status == CacheStatus.EXPIRED:
                return await self._handle_expired_cache(
                    cached_result, cache_key, start_time, degraded_mode_active,
                    data_critical, expected_freshness_hours
                )
                
            else:  # MISSING
                return await self._handle_missing_cache(
                    cache_key, start_time, degraded_mode_active,
                    data_critical, expected_freshness_hours
                )
                
        except Exception as e:
            logger.error(f"Cache get failed for {cache_key}: {e}")
            
            response_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            return build_degraded_response(
                data=None,
                cache_status=CacheStatus.MISSING,
                staleness_warning=None,
                fallback_strategy=CacheFallbackStrategy.RETURN_EMPTY,
                response_source="error",
                response_time_ms=response_time,
                degraded_mode_active=degraded_mode_active
            )
    
    async def put_with_versioning(
        self,
        cache_key: CacheKey,
        data: Any,
        ttl_hours: Optional[int] = None,
        source_system: Optional[str] = None
    ) -> bool:
        """
        Store data in cache with versioning and metadata.
        
        Args:
            cache_key: Key for cached data
            data: Data to cache
            ttl_hours: Time-to-live in hours
            source_system: Source system that provided the data
            
        Returns:
            True if successfully cached
        """
        if not self.redis:
            logger.warning("Redis not available - cannot cache data")
            return False
            
        try:
            ttl = ttl_hours or self.config.default_ttl_hours
            current_time = datetime.utcnow()
            expires_at = current_time + timedelta(hours=ttl)
            
            # Create cached result
            cached_result = CachedResult(
                data=data,
                cache_key=cache_key,
                cached_at=current_time,
                expires_at=expires_at,
                staleness=DataStaleness.CURRENT,
                status=CacheStatus.FRESH,
                source_system=source_system,
                data_version=generate_cache_version_hash(data)
            )
            
            # Serialize and potentially compress
            serialized_data = serialize_cache_data({
                'data': data,
                'cached_at': current_time.isoformat(),
                'expires_at': expires_at.isoformat(),
                'source_system': source_system,
                'data_version': cached_result.data_version
            })
            
            if self.config.compression_enabled and len(serialized_data) > 1024:
                serialized_data = gzip.compress(serialized_data)
                is_compressed = True
            else:
                is_compressed = False
                
            # Store in Redis
            redis_key = cache_key.to_redis_key()
            pipeline = self.redis.pipeline()
            
            # Store main data
            pipeline.setex(
                redis_key,
                ttl * 3600,  # Convert hours to seconds
                serialized_data
            )
            
            # Store metadata
            metadata_key = f"{redis_key}:meta"
            metadata = {
                'compressed': is_compressed,
                'stored_at': current_time.isoformat(),
                'expires_at': expires_at.isoformat(),
                'source_system': source_system or '',
                'data_version': cached_result.data_version,
                'hit_count': 0
            }
            
            pipeline.setex(
                metadata_key,
                ttl * 3600,
                serialize_cache_data(metadata)
            )
            
            await pipeline.execute()
            
            logger.debug(f"Cached data for {cache_key} with TTL {ttl}h")
            return True
            
        except Exception as e:
            logger.error(f"Failed to cache data for {cache_key}: {e}")
            return False
    
    async def invalidate(self, cache_key: CacheKey) -> bool:
        """
        Invalidate cached data.
        
        Args:
            cache_key: Key to invalidate
            
        Returns:
            True if successfully invalidated
        """
        if not self.redis:
            return False
            
        try:
            redis_key = cache_key.to_redis_key()
            pipeline = self.redis.pipeline()
            
            # Delete main data and metadata
            pipeline.delete(redis_key)
            pipeline.delete(f"{redis_key}:meta")
            
            results = await pipeline.execute()
            
            return any(results)  # True if any key was deleted
            
        except Exception as e:
            logger.error(f"Failed to invalidate cache for {cache_key}: {e}")
            return False
    
    async def get_cache_metrics(self) -> CacheMetrics:
        """Get current cache performance metrics."""
        total_requests = self._metrics['total_requests']
        cache_hits = self._metrics['cache_hits']
        stale_hits = self._metrics['stale_hits']
        
        hit_rate = (cache_hits / total_requests) if total_requests > 0 else 0.0
        stale_hit_rate = (stale_hits / total_requests) if total_requests > 0 else 0.0
        
        avg_response_time = (
            self._metrics['total_response_time_ms'] / total_requests
            if total_requests > 0 else 0.0
        )
        
        # Get cache size from Redis if available
        cache_size = 0
        if self.redis:
            try:
                info = await self.redis.info('memory')
                cache_size = info.get('used_memory', 0)
            except Exception:
                pass
                
        return CacheMetrics(
            total_requests=total_requests,
            cache_hits=cache_hits,
            cache_misses=self._metrics['cache_misses'],
            stale_hits=stale_hits,
            expired_items=self._metrics['expired_items'],
            background_refreshes=self._metrics['background_refreshes'],
            average_response_time_ms=avg_response_time,
            cache_size_bytes=cache_size,
            hit_rate=hit_rate,
            stale_hit_rate=stale_hit_rate
        )
    
    async def _get_from_cache(self, cache_key: CacheKey) -> Optional[CachedResult]:
        """Retrieve data from Redis cache."""
        if not self.redis:
            return None
            
        try:
            redis_key = cache_key.to_redis_key()
            
            # Get data and metadata in pipeline
            pipeline = self.redis.pipeline()
            pipeline.get(redis_key)
            pipeline.get(f"{redis_key}:meta")
            pipeline.incr(f"{redis_key}:hits")
            
            results = await pipeline.execute()
            data_bytes, meta_bytes, hit_count = results
            
            if not data_bytes or not meta_bytes:
                return None
                
            # Deserialize metadata
            metadata = deserialize_cache_data(meta_bytes)
            
            # Handle compression
            if metadata.get('compressed', False):
                data_bytes = gzip.decompress(data_bytes)
                
            # Deserialize main data
            cached_data = deserialize_cache_data(data_bytes)
            
            # Build CachedResult
            cached_at = datetime.fromisoformat(cached_data['cached_at'])
            expires_at = datetime.fromisoformat(cached_data['expires_at'])
            
            staleness = calculate_data_staleness(cached_at, datetime.utcnow())
            status = determine_cache_status(None, datetime.utcnow())  # Will be recalculated
            
            return CachedResult(
                data=cached_data['data'],
                cache_key=cache_key,
                cached_at=cached_at,
                expires_at=expires_at,
                staleness=staleness,
                status=status,
                hit_count=hit_count,
                last_accessed=datetime.utcnow(),
                source_system=cached_data.get('source_system'),
                data_version=cached_data.get('data_version')
            )
            
        except Exception as e:
            logger.warning(f"Failed to retrieve from cache {cache_key}: {e}")
            return None
    
    async def _handle_fresh_cache(
        self,
        cached_result: CachedResult,
        cache_key: CacheKey,
        start_time: datetime,
        degraded_mode_active: bool
    ) -> DegradedCacheResponse:
        """Handle fresh cache hit."""
        self._metrics['cache_hits'] += 1
        
        response_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        self._metrics['total_response_time_ms'] += response_time
        
        # Emit cache hit event
        event = CacheHit(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            cache_key=cache_key.to_redis_key(),
            hit_count=cached_result.hit_count,
            data_age_hours=(datetime.utcnow() - cached_result.cached_at).total_seconds() / 3600,
            response_time_ms=response_time
        )
        await self.event_publisher(event)
        
        # Check if background refresh needed
        if should_background_refresh(cached_result, self.config, datetime.utcnow()):
            await self._trigger_background_refresh(cache_key, cached_result)
            
        return build_degraded_response(
            data=cached_result.data,
            cache_status=CacheStatus.FRESH,
            staleness_warning=None,
            fallback_strategy=None,
            response_source="cache",
            response_time_ms=response_time,
            degraded_mode_active=degraded_mode_active
        )
    
    async def _handle_stale_cache(
        self,
        cached_result: CachedResult,
        cache_key: CacheKey,
        start_time: datetime,
        degraded_mode_active: bool,
        data_critical: bool,
        expected_freshness_hours: float
    ) -> DegradedCacheResponse:
        """Handle stale cache data."""
        current_time = datetime.utcnow()
        
        # Check if stale data can be served
        if not can_serve_stale_data(cached_result, self.config, current_time):
            # Too stale to serve - treat as expired
            return await self._handle_expired_cache(
                cached_result, cache_key, start_time, degraded_mode_active,
                data_critical, expected_freshness_hours
            )
        
        self._metrics['stale_hits'] += 1
        response_time = int((current_time - start_time).total_seconds() * 1000)
        self._metrics['total_response_time_ms'] += response_time
        
        # Create staleness warning
        staleness_warning = None
        if should_warn_about_staleness(cached_result, self.config, current_time):
            staleness_warning = create_staleness_warning(
                cached_result, current_time, expected_freshness_hours
            )
            
            # Emit staleness warning event
            warning_event = StalenessWarningIssued(
                event_id=str(uuid.uuid4()),
                timestamp=current_time,
                cache_key=cache_key.to_redis_key(),
                staleness_level=staleness_warning.staleness_level,
                age_hours=staleness_warning.age_hours,
                warning_message=staleness_warning.warning_message
            )
            await self.event_publisher(warning_event)
        
        # Emit stale data served event
        stale_event = StaleDataServed(
            event_id=str(uuid.uuid4()),
            timestamp=current_time,
            cache_key=cache_key.to_redis_key(),
            staleness_level=cached_result.staleness,
            age_hours=(current_time - cached_result.cached_at).total_seconds() / 3600,
            degraded_mode_active=degraded_mode_active
        )
        await self.event_publisher(stale_event)
        
        # Trigger refresh if not in degraded mode
        if not degraded_mode_active:
            await self._trigger_background_refresh(cache_key, cached_result)
            
        return build_degraded_response(
            data=cached_result.data,
            cache_status=CacheStatus.STALE,
            staleness_warning=staleness_warning,
            fallback_strategy=CacheFallbackStrategy.SERVE_STALE,
            response_source="cache_stale",
            response_time_ms=response_time,
            degraded_mode_active=degraded_mode_active
        )
    
    async def _handle_expired_cache(
        self,
        cached_result: Optional[CachedResult],
        cache_key: CacheKey,
        start_time: datetime,
        degraded_mode_active: bool,
        data_critical: bool,
        expected_freshness_hours: float
    ) -> DegradedCacheResponse:
        """Handle expired cache data."""
        self._metrics['expired_items'] += 1
        current_time = datetime.utcnow()
        
        # Choose fallback strategy
        fallback_strategy = choose_fallback_strategy(
            CacheStatus.EXPIRED, degraded_mode_active, data_critical
        )
        
        if fallback_strategy == CacheFallbackStrategy.SERVE_STALE and cached_result:
            # Serve expired data if available
            response_time = int((current_time - start_time).total_seconds() * 1000)
            
            staleness_warning = create_staleness_warning(
                cached_result, current_time, expected_freshness_hours
            )
            
            return build_degraded_response(
                data=cached_result.data,
                cache_status=CacheStatus.EXPIRED,
                staleness_warning=staleness_warning,
                fallback_strategy=fallback_strategy,
                response_source="cache_expired",
                response_time_ms=response_time,
                degraded_mode_active=degraded_mode_active
            )
            
        else:
            # Use fallback data source or return empty
            return await self._use_fallback_data_source(
                cache_key, start_time, degraded_mode_active, fallback_strategy
            )
    
    async def _handle_missing_cache(
        self,
        cache_key: CacheKey,
        start_time: datetime,
        degraded_mode_active: bool,
        data_critical: bool,
        expected_freshness_hours: float
    ) -> DegradedCacheResponse:
        """Handle missing cache data."""
        self._metrics['cache_misses'] += 1
        
        # Choose fallback strategy
        fallback_strategy = choose_fallback_strategy(
            CacheStatus.MISSING, degraded_mode_active, data_critical
        )
        
        # Emit cache miss event
        miss_event = CacheMiss(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            cache_key=cache_key.to_redis_key(),
            fallback_strategy=fallback_strategy,
            degraded_mode_active=degraded_mode_active
        )
        await self.event_publisher(miss_event)
        
        return await self._use_fallback_data_source(
            cache_key, start_time, degraded_mode_active, fallback_strategy
        )
    
    async def _use_fallback_data_source(
        self,
        cache_key: CacheKey,
        start_time: datetime,
        degraded_mode_active: bool,
        fallback_strategy: CacheFallbackStrategy
    ) -> DegradedCacheResponse:
        """Use fallback data source when cache unavailable."""
        response_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        if fallback_strategy == CacheFallbackStrategy.USE_RSS_FALLBACK and self.fallback_data_source:
            try:
                # Use RSS fallback data
                fallback_data = await self.fallback_data_source(cache_key)
                
                return build_degraded_response(
                    data=fallback_data,
                    cache_status=CacheStatus.MISSING,
                    staleness_warning=None,
                    fallback_strategy=fallback_strategy,
                    response_source="rss_fallback",
                    response_time_ms=response_time,
                    degraded_mode_active=degraded_mode_active
                )
                
            except Exception as e:
                logger.error(f"Fallback data source failed: {e}")
                
        # Return empty response with appropriate strategy
        return build_degraded_response(
            data=None,
            cache_status=CacheStatus.MISSING,
            staleness_warning=None,
            fallback_strategy=fallback_strategy,
            response_source="empty",
            response_time_ms=response_time,
            degraded_mode_active=degraded_mode_active
        )
    
    async def _trigger_background_refresh(
        self,
        cache_key: CacheKey,
        current_cached_result: CachedResult
    ) -> None:
        """Trigger background refresh of cached data."""
        self._metrics['background_refreshes'] += 1
        
        refresh_request = BackgroundRefreshRequest(
            cache_key=cache_key,
            current_data=current_cached_result.data,
            refresh_source="automatic",
            priority=1 if current_cached_result.status == CacheStatus.EXPIRED else 2,
            requested_at=datetime.utcnow(),
            estimated_refresh_time_ms=5000  # Estimate 5 seconds
        )
        
        # Emit refresh event
        refresh_event = CacheRefreshTriggered(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            cache_key=cache_key.to_redis_key(),
            refresh_reason="background_refresh",
            current_data_age_hours=(
                datetime.utcnow() - current_cached_result.cached_at
            ).total_seconds() / 3600
        )
        await self.event_publisher(refresh_event)
        
        logger.debug(f"Triggered background refresh for {cache_key}")
    
    async def _default_event_publisher(self, event) -> None:
        """Default event publisher that logs events."""
        logger.info(f"Cache Event: {type(event).__name__} - {event}")


# Global cache manager instance
_global_cache_manager: Optional[DegradedCacheManager] = None


async def get_cached_with_degraded_handling(
    cache_key: CacheKey,
    data_critical: bool = False,
    degraded_mode_active: bool = False,
    expected_freshness_hours: float = 6.0
) -> DegradedCacheResponse[Any]:
    """
    Global function to get cached data with degraded mode handling.
    
    Args:
        cache_key: Key for cached data
        data_critical: Whether this data is critical
        degraded_mode_active: Whether system is in degraded mode
        expected_freshness_hours: Expected data freshness
        
    Returns:
        DegradedCacheResponse with data and context
    """
    global _global_cache_manager
    
    if _global_cache_manager is None:
        _global_cache_manager = DegradedCacheManager()
        
    return await _global_cache_manager.get_with_degraded_handling(
        cache_key, data_critical, degraded_mode_active, expected_freshness_hours
    )


def initialize_cache_manager(
    redis_client: Optional[redis.Redis] = None,
    config: Optional[CacheConfig] = None,
    event_publisher: Optional[Callable] = None,
    fallback_data_source: Optional[Callable] = None
) -> DegradedCacheManager:
    """Initialize the global cache manager."""
    global _global_cache_manager
    _global_cache_manager = DegradedCacheManager(
        redis_client, config, event_publisher, fallback_data_source
    )
    return _global_cache_manager