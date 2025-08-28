"""
RSS Fallback System - Type Definitions and Contracts

Defines types and interfaces for RSS feed fallback when Parallel.ai unavailable.
"""

from dataclasses import dataclass
from typing import List, Optional, Protocol, Dict, Any
from enum import Enum
from datetime import datetime


class FeedType(Enum):
    """Types of RSS feeds supported."""
    NBB_NEWS = "nbb_news"
    FSMA_NEWS = "fsma_news" 
    EUR_LEX_UPDATES = "eur_lex_updates"
    EBA_GUIDANCE = "eba_guidance"


class ContentRelevance(Enum):
    """Relevance levels for RSS content."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    IGNORE = "ignore"


@dataclass(frozen=True)
class RSSFeedConfig:
    """Configuration for RSS feed source."""
    
    feed_type: FeedType
    url: str
    domain: str
    authority: str
    languages: List[str]
    update_interval_minutes: int
    timeout_seconds: int = 30
    max_items: int = 100
    
    
@dataclass(frozen=True) 
class RSSItem:
    """Individual RSS feed item."""
    
    title: str
    link: str
    description: str
    published_date: datetime
    guid: str
    content: Optional[str] = None
    language: Optional[str] = None
    tags: List[str] = None
    
    def __post_init__(self):
        """Set default empty list for tags."""
        if self.tags is None:
            object.__setattr__(self, 'tags', [])


@dataclass(frozen=True)
class ProcessedRSSItem:
    """RSS item after processing and relevance scoring."""
    
    rss_item: RSSItem
    relevance: ContentRelevance
    relevance_score: float
    extracted_keywords: List[str] 
    regulatory_indicators: List[str]
    source_feed: FeedType
    processed_at: datetime
    content_hash: str
    

@dataclass(frozen=True)
class RSSParseResult:
    """Result of parsing RSS feed."""
    
    feed_config: RSSFeedConfig
    items: List[RSSItem]
    parse_timestamp: datetime
    feed_last_updated: Optional[datetime]
    parse_duration_ms: int
    errors: List[str] = None
    
    def __post_init__(self):
        """Set default empty list for errors."""
        if self.errors is None:
            object.__setattr__(self, 'errors', [])


@dataclass(frozen=True)
class DegradedModeConfig:
    """Configuration for degraded mode RSS fallback."""
    
    enabled: bool = True
    fallback_timeout_minutes: int = 5
    max_cache_age_hours: int = 24
    relevance_threshold: float = 0.5
    max_items_per_feed: int = 50
    
    
class RSSParser(Protocol):
    """Protocol for RSS feed parsing implementations."""
    
    def parse_feed(self, config: RSSFeedConfig) -> RSSParseResult:
        """Parse RSS feed from URL."""
        ...
        
    def extract_content(self, item: RSSItem) -> Optional[str]:
        """Extract full content from RSS item link."""
        ...


class ContentAnalyzer(Protocol):
    """Protocol for analyzing RSS content relevance."""
    
    def analyze_relevance(self, item: RSSItem) -> ContentRelevance:
        """Determine content relevance for regulatory monitoring."""
        ...
        
    def extract_regulatory_indicators(self, content: str) -> List[str]:
        """Extract regulatory keywords and indicators."""
        ...
        
    def calculate_relevance_score(self, item: RSSItem) -> float:
        """Calculate numerical relevance score 0.0-1.0."""
        ...


@dataclass(frozen=True)  
class FallbackMetrics:
    """Metrics for RSS fallback system performance."""
    
    total_feeds_processed: int
    total_items_found: int
    high_relevance_items: int
    processing_time_ms: int
    cache_hit_rate: float
    errors_encountered: int
    last_successful_update: Optional[datetime] = None