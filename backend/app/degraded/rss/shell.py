"""
RSS Fallback System - I/O Operations

Handles RSS feed fetching, parsing, caching, and integration with circuit breaker.
"""

import asyncio
import logging
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Callable
from urllib.parse import urljoin, urlparse

try:
    import feedparser
    import httpx
    import redis.asyncio as redis
except ImportError:
    feedparser = None
    httpx = None
    redis = None

from ..parallel.common.shell import assert_parallel_safe
from .contracts import (
    RSSFeedConfig,
    RSSItem,
    RSSParseResult,
    ProcessedRSSItem,
    FeedType,
    ContentRelevance,
    DegradedModeConfig,
    FallbackMetrics
)
from .core import (
    process_rss_item,
    filter_relevant_items,
    deduplicate_items,
    build_fallback_metrics
)
from .events import (
    RSSFallbackActivated,
    RSSFeedProcessed,
    RSSFeedFailed,
    HighRelevanceContentDetected,
    RSSContentCacheUpdated,
    RSSParsingError
)

logger = logging.getLogger(__name__)


class RSSFallbackError(Exception):
    """Raised when RSS fallback system encounters errors."""
    
    def __init__(self, feed_type: FeedType, message: str, original_error: Exception = None):
        self.feed_type = feed_type
        self.original_error = original_error
        super().__init__(f"RSS fallback error for {feed_type.value}: {message}")


class RSSFeedManager:
    """
    Manages RSS feed fallback operations with caching and circuit breaker integration.
    
    This class provides RSS fallback capabilities when Parallel.ai is unavailable,
    ensuring continuous regulatory monitoring through RSS feeds.
    """
    
    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None,
        http_client: Optional[httpx.AsyncClient] = None,
        config: Optional[DegradedModeConfig] = None,
        event_publisher: Optional[Callable] = None
    ):
        self.redis = redis_client
        self.http_client = http_client or httpx.AsyncClient(timeout=30.0)
        self.config = config or DegradedModeConfig()
        self.event_publisher = event_publisher or self._default_event_publisher
        
        # RSS feed configurations
        self.feed_configs = self._build_feed_configs()
        
    def _build_feed_configs(self) -> Dict[FeedType, RSSFeedConfig]:
        """Build RSS feed configuration for each supported source."""
        return {
            FeedType.NBB_NEWS: RSSFeedConfig(
                feed_type=FeedType.NBB_NEWS,
                url="https://www.nbb.be/rss/news",
                domain="nbb.be",
                authority="NBB", 
                languages=["en", "nl", "fr"],
                update_interval_minutes=30,
                timeout_seconds=30
            ),
            FeedType.FSMA_NEWS: RSSFeedConfig(
                feed_type=FeedType.FSMA_NEWS,
                url="https://www.fsma.be/rss/news", 
                domain="fsma.be",
                authority="FSMA",
                languages=["en", "nl", "fr"],
                update_interval_minutes=30,
                timeout_seconds=30
            ),
            FeedType.EUR_LEX_UPDATES: RSSFeedConfig(
                feed_type=FeedType.EUR_LEX_UPDATES,
                url="https://eur-lex.europa.eu/rss/latest-legislation.xml",
                domain="eur-lex.europa.eu", 
                authority="EU_COMMISSION",
                languages=["en"],
                update_interval_minutes=60,
                timeout_seconds=45
            ),
            FeedType.EBA_GUIDANCE: RSSFeedConfig(
                feed_type=FeedType.EBA_GUIDANCE,
                url="https://www.eba.europa.eu/rss.xml",
                domain="eba.europa.eu",
                authority="EBA", 
                languages=["en"],
                update_interval_minutes=120,
                timeout_seconds=30
            )
        }
    
    async def activate_rss_fallback(
        self,
        trigger_service: str = "parallel_ai",
        reason: str = "Circuit breaker open"
    ) -> None:
        """
        Activate RSS fallback mode due to primary service failure.
        
        Args:
            trigger_service: Name of service that triggered fallback
            reason: Reason for activation
        """
        if not self.config.enabled:
            logger.warning("RSS fallback is disabled in configuration")
            return
            
        # Estimate coverage based on available feeds
        active_feeds = [feed for feed in self.feed_configs.keys()]
        coverage_estimate = min(0.8, len(active_feeds) / 4.0)  # Max 80% coverage
        
        event = RSSFallbackActivated(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            trigger_service=trigger_service,
            reason=reason,
            affected_feeds=active_feeds,
            estimated_coverage_percentage=coverage_estimate,
            context={"config": self.config.__dict__}
        )
        
        await self.event_publisher(event)
        logger.info(f"RSS fallback activated: {reason}")
        
        # Start monitoring RSS feeds
        await self._start_feed_monitoring()
    
    async def process_all_feeds(self) -> List[ProcessedRSSItem]:
        """
        Process all configured RSS feeds and return relevant items.
        
        Returns:
            List of processed and filtered RSS items
        """
        all_items = []
        processing_start = datetime.utcnow()
        
        # Process feeds concurrently
        tasks = []
        for feed_type, config in self.feed_configs.items():
            task = asyncio.create_task(
                self._process_single_feed(config),
                name=f"process_{feed_type.value}"
            )
            tasks.append(task)
            
        # Wait for all feeds to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Collect successful results
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                feed_type = list(self.feed_configs.keys())[i]
                logger.error(f"Feed processing failed for {feed_type}: {result}")
                continue
                
            if isinstance(result, list):
                all_items.extend(result)
        
        # Deduplicate and filter
        unique_items = deduplicate_items(all_items)
        relevant_items = filter_relevant_items(
            unique_items,
            min_relevance=ContentRelevance.MEDIUM
        )
        
        # Cache results
        if relevant_items:
            await self._cache_processed_items(relevant_items)
            
        processing_end = datetime.utcnow()
        
        # Emit metrics event  
        metrics = build_fallback_metrics(
            relevant_items, 
            processing_start,
            processing_end
        )
        
        logger.info(
            f"RSS fallback processed {len(all_items)} items, "
            f"{len(relevant_items)} relevant"
        )
        
        return relevant_items
        
    async def _process_single_feed(self, config: RSSFeedConfig) -> List[ProcessedRSSItem]:
        """
        Process a single RSS feed.
        
        Args:
            config: RSS feed configuration
            
        Returns:
            List of processed items from this feed
        """
        try:
            # Check cache first
            cached_items = await self._get_cached_items(config.feed_type)
            if cached_items and self._is_cache_fresh(cached_items):
                logger.debug(f"Using cached items for {config.feed_type.value}")
                return cached_items
                
            # Fetch and parse feed
            parse_result = await self._fetch_and_parse_feed(config)
            
            if not parse_result.items:
                logger.warning(f"No items found in feed {config.feed_type.value}")
                return []
                
            # Process items
            processed_items = []
            for rss_item in parse_result.items:
                try:
                    processed_item = process_rss_item(rss_item, config.feed_type)
                    processed_items.append(processed_item)
                    
                    # Emit event for high-relevance items
                    if processed_item.relevance == ContentRelevance.HIGH:
                        await self._emit_high_relevance_event(processed_item)
                        
                except Exception as e:
                    logger.warning(f"Failed to process RSS item: {e}")
                    continue
                    
            # Emit processing event
            event = RSSFeedProcessed(
                event_id=str(uuid.uuid4()),
                timestamp=datetime.utcnow(),
                feed_type=config.feed_type,
                feed_url=config.url,
                items_found=len(parse_result.items),
                relevant_items=len([item for item in processed_items 
                                  if item.relevance != ContentRelevance.IGNORE]),
                high_relevance_items=len([item for item in processed_items
                                        if item.relevance == ContentRelevance.HIGH]),
                processing_time_ms=parse_result.parse_duration_ms,
                content_hash=self._calculate_feed_hash(processed_items)
            )
            await self.event_publisher(event)
            
            return processed_items
            
        except Exception as e:
            # Emit failure event
            event = RSSFeedFailed(
                event_id=str(uuid.uuid4()),
                timestamp=datetime.utcnow(),
                feed_type=config.feed_type,
                feed_url=config.url,
                error_type=type(e).__name__,
                error_message=str(e)
            )
            await self.event_publisher(event)
            
            logger.error(f"RSS feed processing failed for {config.feed_type}: {e}")
            return []
    
    async def _fetch_and_parse_feed(self, config: RSSFeedConfig) -> RSSParseResult:
        """
        Fetch RSS feed content and parse into RSSItem objects.
        
        Args:
            config: RSS feed configuration
            
        Returns:
            RSSParseResult with parsed items
        """
        if not feedparser:
            raise RSSFallbackError(
                config.feed_type,
                "feedparser library not available"
            )
            
        start_time = datetime.utcnow()
        
        try:
            # Fetch RSS content
            response = await self.http_client.get(
                config.url,
                timeout=config.timeout_seconds,
                follow_redirects=True
            )
            response.raise_for_status()
            
            # Parse RSS content
            feed_content = response.text
            parsed_feed = feedparser.parse(feed_content)
            
            if parsed_feed.bozo and parsed_feed.bozo_exception:
                logger.warning(
                    f"RSS parsing warning for {config.feed_type}: "
                    f"{parsed_feed.bozo_exception}"
                )
            
            # Convert to RSSItem objects
            items = []
            for entry in parsed_feed.entries[:config.max_items]:
                try:
                    rss_item = self._convert_feed_entry(entry, config)
                    if rss_item:
                        items.append(rss_item)
                except Exception as e:
                    logger.warning(f"Failed to convert RSS entry: {e}")
                    continue
                    
            # Get feed metadata
            feed_updated = None
            if hasattr(parsed_feed.feed, 'updated_parsed') and parsed_feed.feed.updated_parsed:
                try:
                    import time
                    feed_updated = datetime.fromtimestamp(
                        time.mktime(parsed_feed.feed.updated_parsed)
                    )
                except Exception:
                    pass
                    
            parse_duration = int(
                (datetime.utcnow() - start_time).total_seconds() * 1000
            )
            
            return RSSParseResult(
                feed_config=config,
                items=items,
                parse_timestamp=datetime.utcnow(),
                feed_last_updated=feed_updated,
                parse_duration_ms=parse_duration,
                errors=[]
            )
            
        except Exception as e:
            parse_duration = int(
                (datetime.utcnow() - start_time).total_seconds() * 1000
            )
            
            return RSSParseResult(
                feed_config=config,
                items=[],
                parse_timestamp=datetime.utcnow(), 
                feed_last_updated=None,
                parse_duration_ms=parse_duration,
                errors=[str(e)]
            )
    
    def _convert_feed_entry(self, entry, config: RSSFeedConfig) -> Optional[RSSItem]:
        """Convert feedparser entry to RSSItem."""
        try:
            # Extract publication date
            published_date = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                import time
                published_date = datetime.fromtimestamp(
                    time.mktime(entry.published_parsed)
                )
            elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                import time  
                published_date = datetime.fromtimestamp(
                    time.mktime(entry.updated_parsed)
                )
                
            # Extract content
            content = ""
            if hasattr(entry, 'content') and entry.content:
                content = entry.content[0].value if entry.content else ""
            elif hasattr(entry, 'summary') and entry.summary:
                content = entry.summary
                
            # Extract GUID
            guid = getattr(entry, 'guid', getattr(entry, 'id', entry.link))
            
            return RSSItem(
                title=getattr(entry, 'title', ''),
                link=getattr(entry, 'link', ''),
                description=getattr(entry, 'summary', ''),
                published_date=published_date,
                guid=guid,
                content=content,
                language=None,  # Could extract from feed metadata
                tags=getattr(entry, 'tags', [])
            )
            
        except Exception as e:
            logger.warning(f"Failed to convert RSS entry: {e}")
            return None
    
    async def _emit_high_relevance_event(self, item: ProcessedRSSItem) -> None:
        """Emit event for high-relevance content detection."""
        event = HighRelevanceContentDetected(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            feed_type=item.source_feed,
            item_title=item.rss_item.title,
            item_link=item.rss_item.link,
            relevance_score=item.relevance_score,
            regulatory_indicators=item.regulatory_indicators,
            published_date=item.rss_item.published_date
        )
        await self.event_publisher(event)
        
    async def _cache_processed_items(self, items: List[ProcessedRSSItem]) -> None:
        """Cache processed items in Redis."""
        if not self.redis or not items:
            return
            
        try:
            cache_key = "rss_fallback:processed_items"
            
            # Serialize items for caching
            cache_data = {
                "items": [self._serialize_processed_item(item) for item in items],
                "cached_at": datetime.utcnow().isoformat(),
                "expires_at": (
                    datetime.utcnow() + 
                    timedelta(hours=self.config.max_cache_age_hours)
                ).isoformat()
            }
            
            import json
            await self.redis.setex(
                cache_key,
                self.config.max_cache_age_hours * 3600,
                json.dumps(cache_data, default=str)
            )
            
            # Emit cache update event
            event = RSSContentCacheUpdated(
                event_id=str(uuid.uuid4()),
                timestamp=datetime.utcnow(),
                feed_type=items[0].source_feed if items else FeedType.NBB_NEWS,
                items_cached=len(items),
                cache_size_after_update=len(items),
                oldest_item_age_hours=self._calculate_oldest_item_age(items),
                cache_hit_rate=1.0  # This is a cache write
            )
            await self.event_publisher(event)
            
        except Exception as e:
            logger.warning(f"Failed to cache RSS items: {e}")
    
    async def _get_cached_items(self, feed_type: FeedType) -> Optional[List[ProcessedRSSItem]]:
        """Retrieve cached processed items."""
        if not self.redis:
            return None
            
        try:
            cache_key = "rss_fallback:processed_items"
            cached_data = await self.redis.get(cache_key)
            
            if not cached_data:
                return None
                
            import json
            cache_obj = json.loads(cached_data)
            
            # Check if cache is expired
            expires_at = datetime.fromisoformat(cache_obj["expires_at"])
            if datetime.utcnow() > expires_at:
                return None
                
            # Deserialize items
            items = []
            for item_data in cache_obj["items"]:
                try:
                    item = self._deserialize_processed_item(item_data)
                    if item.source_feed == feed_type:
                        items.append(item)
                except Exception as e:
                    logger.warning(f"Failed to deserialize cached item: {e}")
                    continue
                    
            return items
            
        except Exception as e:
            logger.warning(f"Failed to retrieve cached items: {e}")
            return None
    
    def _serialize_processed_item(self, item: ProcessedRSSItem) -> Dict[str, Any]:
        """Serialize ProcessedRSSItem for caching."""
        return {
            "rss_item": {
                "title": item.rss_item.title,
                "link": item.rss_item.link,
                "description": item.rss_item.description,
                "published_date": item.rss_item.published_date.isoformat() if item.rss_item.published_date else None,
                "guid": item.rss_item.guid,
                "content": item.rss_item.content,
                "language": item.rss_item.language,
                "tags": item.rss_item.tags
            },
            "relevance": item.relevance.value,
            "relevance_score": item.relevance_score,
            "extracted_keywords": item.extracted_keywords,
            "regulatory_indicators": item.regulatory_indicators,
            "source_feed": item.source_feed.value,
            "processed_at": item.processed_at.isoformat(),
            "content_hash": item.content_hash
        }
    
    def _deserialize_processed_item(self, data: Dict[str, Any]) -> ProcessedRSSItem:
        """Deserialize ProcessedRSSItem from cache data."""
        rss_item_data = data["rss_item"]
        rss_item = RSSItem(
            title=rss_item_data["title"],
            link=rss_item_data["link"],
            description=rss_item_data["description"],
            published_date=datetime.fromisoformat(rss_item_data["published_date"]) if rss_item_data["published_date"] else None,
            guid=rss_item_data["guid"],
            content=rss_item_data["content"],
            language=rss_item_data["language"],
            tags=rss_item_data["tags"] or []
        )
        
        return ProcessedRSSItem(
            rss_item=rss_item,
            relevance=ContentRelevance(data["relevance"]),
            relevance_score=data["relevance_score"], 
            extracted_keywords=data["extracted_keywords"],
            regulatory_indicators=data["regulatory_indicators"],
            source_feed=FeedType(data["source_feed"]),
            processed_at=datetime.fromisoformat(data["processed_at"]),
            content_hash=data["content_hash"]
        )
    
    def _is_cache_fresh(self, items: List[ProcessedRSSItem]) -> bool:
        """Check if cached items are still fresh."""
        if not items:
            return False
            
        oldest_acceptable = datetime.utcnow() - timedelta(
            hours=self.config.max_cache_age_hours
        )
        
        return all(item.processed_at > oldest_acceptable for item in items)
    
    def _calculate_oldest_item_age(self, items: List[ProcessedRSSItem]) -> float:
        """Calculate age of oldest item in hours."""
        if not items:
            return 0.0
            
        oldest = min(items, key=lambda x: x.processed_at)
        age_delta = datetime.utcnow() - oldest.processed_at
        return age_delta.total_seconds() / 3600
    
    def _calculate_feed_hash(self, items: List[ProcessedRSSItem]) -> str:
        """Calculate hash for feed content to detect changes."""
        if not items:
            return ""
            
        content_hashes = sorted([item.content_hash for item in items])
        combined_content = "|".join(content_hashes)
        
        import hashlib
        return hashlib.sha256(combined_content.encode('utf-8')).hexdigest()
    
    async def _start_feed_monitoring(self) -> None:
        """Start periodic RSS feed monitoring."""
        logger.info("Starting RSS feed monitoring for degraded mode")
        # Implementation would start background tasks for periodic monitoring
        # This would be integrated with the scheduler service
    
    async def _default_event_publisher(self, event) -> None:
        """Default event publisher that logs events."""
        logger.info(f"RSS Fallback Event: {type(event).__name__} - {event}")


# Global RSS feed manager instance
_global_rss_manager: Optional[RSSFeedManager] = None


async def get_rss_fallback_content(
    min_relevance: ContentRelevance = ContentRelevance.MEDIUM
) -> List[ProcessedRSSItem]:
    """
    Get RSS fallback content for degraded mode operation.
    
    This is the main entry point for retrieving regulatory content
    when Parallel.ai is unavailable.
    
    Args:
        min_relevance: Minimum relevance level to return
        
    Returns:
        List of relevant processed RSS items
    """
    global _global_rss_manager
    
    if _global_rss_manager is None:
        _global_rss_manager = RSSFeedManager()
        
    items = await _global_rss_manager.process_all_feeds()
    return filter_relevant_items(items, min_relevance)


def initialize_rss_manager(
    redis_client: Optional[redis.Redis] = None,
    http_client: Optional[httpx.AsyncClient] = None,
    config: Optional[DegradedModeConfig] = None,
    event_publisher: Optional[Callable] = None
) -> RSSFeedManager:
    """Initialize the global RSS feed manager."""
    global _global_rss_manager
    _global_rss_manager = RSSFeedManager(redis_client, http_client, config, event_publisher)
    return _global_rss_manager