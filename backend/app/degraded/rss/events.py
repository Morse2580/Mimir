"""
RSS Fallback System - Domain Events

Events emitted by the RSS fallback system for monitoring and observability.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any

from .contracts import FeedType, ContentRelevance


@dataclass(frozen=True)
class RSSFallbackActivated:
    """
    Event emitted when RSS fallback system is activated due to service failure.
    
    This indicates the system has switched to degraded mode and is using
    RSS feeds instead of the primary Parallel.ai service.
    """
    
    event_id: str
    timestamp: datetime
    trigger_service: str  # e.g., "parallel_ai" 
    reason: str
    affected_feeds: List[FeedType]
    estimated_coverage_percentage: float
    context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class RSSFeedProcessed:
    """
    Event emitted when RSS feed is successfully processed.
    
    Provides metrics and results of RSS feed parsing and analysis.
    """
    
    event_id: str
    timestamp: datetime
    feed_type: FeedType
    feed_url: str
    items_found: int
    relevant_items: int
    high_relevance_items: int
    processing_time_ms: int
    content_hash: str  # Hash of processed content for change detection
    context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True) 
class RSSFeedFailed:
    """
    Event emitted when RSS feed processing fails.
    
    Critical for monitoring feed availability and fallback system health.
    """
    
    event_id: str
    timestamp: datetime
    feed_type: FeedType
    feed_url: str
    error_type: str
    error_message: str
    retry_count: int = 0
    will_retry: bool = False
    context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class HighRelevanceContentDetected:
    """
    Event emitted when high-relevance regulatory content is found via RSS.
    
    This should trigger alerts as it may indicate important regulatory changes
    that need immediate attention.
    """
    
    event_id: str
    timestamp: datetime
    feed_type: FeedType
    item_title: str
    item_link: str
    relevance_score: float
    regulatory_indicators: List[str]
    published_date: Optional[datetime] = None
    context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class RSSFallbackDeactivated:
    """
    Event emitted when RSS fallback is deactivated and primary service restored.
    
    Indicates return to normal operation mode.
    """
    
    event_id: str
    timestamp: datetime
    primary_service: str
    fallback_duration_seconds: int
    items_processed_during_fallback: int
    successful_feeds: int
    failed_feeds: int
    context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class RSSContentCacheUpdated:
    """
    Event emitted when RSS content cache is updated with new items.
    
    Tracks cache operations and freshness for degraded mode operations.
    """
    
    event_id: str
    timestamp: datetime
    feed_type: FeedType
    items_cached: int
    cache_size_after_update: int
    oldest_item_age_hours: float
    cache_hit_rate: float
    context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class RSSParsingError:
    """
    Event emitted when RSS feed parsing encounters errors.
    
    Detailed error information for debugging and monitoring.
    """
    
    event_id: str
    timestamp: datetime
    feed_type: FeedType
    feed_url: str
    parsing_stage: str  # e.g., "fetch", "parse", "analyze"
    error_details: str
    content_preview: Optional[str] = None  # First 200 chars for debugging
    context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class DegradedModeMetrics:
    """
    Event emitted periodically with degraded mode performance metrics.
    
    Provides aggregated statistics for monitoring and alerting.
    """
    
    event_id: str
    timestamp: datetime
    active_duration_seconds: int
    total_feeds_monitored: int
    successful_feed_updates: int
    failed_feed_updates: int
    total_items_processed: int
    high_relevance_items_found: int
    average_processing_time_ms: float
    cache_hit_rate: float
    estimated_coverage_vs_normal: float
    context: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Validate metrics data."""
        if self.estimated_coverage_vs_normal < 0 or self.estimated_coverage_vs_normal > 1:
            raise ValueError("Coverage percentage must be between 0 and 1")
        if self.cache_hit_rate < 0 or self.cache_hit_rate > 1:
            raise ValueError("Cache hit rate must be between 0 and 1")