"""
RSS Fallback System - Core Processing Functions

Pure functions for RSS parsing, content analysis, and relevance scoring.
"""

import hashlib
import re
from datetime import datetime
from typing import List, Tuple, Dict, Optional
from urllib.parse import urlparse

from .contracts import (
    RSSItem,
    ProcessedRSSItem, 
    ContentRelevance,
    FeedType,
    RSSFeedConfig,
    FallbackMetrics
)


def calculate_relevance_score(item: RSSItem) -> float:
    """
    Calculate relevance score for RSS item (0.0-1.0).
    
    Args:
        item: RSS item to analyze
        
    Returns:
        Relevance score from 0.0 (irrelevant) to 1.0 (highly relevant)
        
    MUST be deterministic - same input produces same output.
    """
    if not item:
        return 0.0
        
    score = 0.0
    content = f"{item.title} {item.description} {item.content or ''}"
    content_lower = content.lower()
    
    # High-impact regulatory keywords
    high_impact_keywords = [
        "dora", "nis2", "gdpr", "mifid", "basel", "solvency",
        "regulation", "directive", "circular", "technical standards",
        "supervisory", "compliance", "operational resilience",
        "ict risk", "incident reporting", "third party",
        "outsourcing", "cloud", "cyber", "security"
    ]
    
    high_matches = sum(1 for keyword in high_impact_keywords 
                      if keyword in content_lower)
    score += min(1.0, high_matches * 0.15)  # Up to 1.0 for high-impact terms
    
    # Medium-impact keywords
    medium_impact_keywords = [
        "guidance", "consultation", "framework", "guidelines",
        "requirements", "obligations", "procedures", "measures",
        "assessment", "monitoring", "reporting", "notification"
    ]
    
    medium_matches = sum(1 for keyword in medium_impact_keywords
                        if keyword in content_lower)
    score += min(0.6, medium_matches * 0.08)  # Up to 0.6 for medium-impact
    
    # Belgian/EU authority mentions
    authority_keywords = [
        "nbb", "fsma", "ccb", "eba", "esma", "eiopa", 
        "european commission", "european banking authority",
        "national bank", "financial markets", "belgium", "belgian"
    ]
    
    authority_matches = sum(1 for keyword in authority_keywords
                           if keyword in content_lower)
    score += min(0.4, authority_matches * 0.1)  # Up to 0.4 for authorities
    
    # Date recency bonus (newer items score higher)
    if item.published_date:
        days_old = (datetime.utcnow() - item.published_date).days
        if days_old <= 1:
            score += 0.1  # Bonus for very recent items
        elif days_old <= 7:
            score += 0.05  # Smaller bonus for recent items
            
    # Content length indicator (longer content often more substantive)
    if len(content) > 500:
        score += 0.05
    elif len(content) > 200:
        score += 0.02
        
    return min(1.0, score)


def classify_content_relevance(relevance_score: float) -> ContentRelevance:
    """
    Classify content relevance based on score.
    
    Args:
        relevance_score: Numerical relevance score 0.0-1.0
        
    Returns:
        ContentRelevance enum value
        
    MUST be deterministic.
    """
    if relevance_score >= 0.7:
        return ContentRelevance.HIGH
    elif relevance_score >= 0.4:
        return ContentRelevance.MEDIUM  
    elif relevance_score >= 0.2:
        return ContentRelevance.LOW
    else:
        return ContentRelevance.IGNORE


def extract_regulatory_indicators(content: str) -> List[str]:
    """
    Extract regulatory keywords and indicators from content.
    
    Args:
        content: Text content to analyze
        
    Returns:
        List of regulatory indicators found
        
    MUST be deterministic.
    """
    if not content or not isinstance(content, str):
        return []
        
    indicators = []
    content_lower = content.lower()
    
    # Regulation references
    reg_patterns = [
        r"regulation\s+\(?eu\)?\s*(\d{4}/\d+|\d+/\d{4})",  # EU regulations  
        r"directive\s+\(?eu\)?\s*(\d{4}/\d+|\d+/\d{4})",   # EU directives
        r"dora\s*(?:regulation)?",                          # DORA
        r"nis\s*2?\s*(?:directive)?",                       # NIS2
        r"gdpr\s*(?:regulation)?",                          # GDPR
        r"mifid\s*ii?\s*(?:directive)?",                    # MiFID
        r"basel\s*iii?\s*(?:framework)?",                   # Basel
        r"solvency\s*ii?\s*(?:directive)?",                 # Solvency II
    ]
    
    for pattern in reg_patterns:
        matches = re.finditer(pattern, content_lower)
        for match in matches:
            indicators.append(match.group().upper())
            
    # Compliance terms
    compliance_terms = [
        "incident reporting", "operational resilience", "ict risk",
        "third party risk", "outsourcing", "cloud services",
        "cyber security", "business continuity", "recovery",
        "supervisory review", "technical standards"
    ]
    
    for term in compliance_terms:
        if term in content_lower:
            indicators.append(term.title())
            
    # Deadlines and dates
    deadline_patterns = [
        r"by\s+(\d{1,2}\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4})",
        r"deadline[:\s]+(\d{1,2}[/.-]\d{1,2}[/.-]\d{4})",
        r"effective\s+(?:from\s+)?(\d{1,2}\s+\w+\s+\d{4})"
    ]
    
    for pattern in deadline_patterns:
        matches = re.finditer(pattern, content_lower)
        for match in matches:
            indicators.append(f"Deadline: {match.group(1)}")
            
    return sorted(list(set(indicators)))  # Remove duplicates and sort


def extract_keywords(content: str, max_keywords: int = 10) -> List[str]:
    """
    Extract key terms from content for indexing and search.
    
    Args:
        content: Text content to analyze
        max_keywords: Maximum number of keywords to return
        
    Returns:
        List of extracted keywords
        
    MUST be deterministic.
    """
    if not content or not isinstance(content, str):
        return []
        
    # Remove common words
    stop_words = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
        "for", "of", "with", "by", "this", "that", "is", "are", "was",
        "were", "be", "been", "have", "has", "had", "will", "would",
        "could", "should", "may", "might", "can", "must", "shall"
    }
    
    # Extract words, normalize and filter
    words = re.findall(r'\b[a-zA-Z]{3,}\b', content.lower())
    keywords = []
    
    for word in words:
        if word not in stop_words and len(word) >= 3:
            keywords.append(word)
            
    # Count frequency and take most common
    word_counts = {}
    for word in keywords:
        word_counts[word] = word_counts.get(word, 0) + 1
        
    # Sort by frequency and take top keywords
    sorted_keywords = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)
    
    return [word for word, count in sorted_keywords[:max_keywords]]


def generate_content_hash(item: RSSItem) -> str:
    """
    Generate deterministic hash for RSS item content.
    
    Args:
        item: RSS item to hash
        
    Returns:
        SHA-256 hash of item content
        
    MUST be deterministic.
    """
    if not item:
        return ""
        
    # Combine key fields that indicate content changes
    content_parts = [
        item.title or "",
        item.description or "",
        item.content or "",
        item.link or "",
        item.published_date.isoformat() if item.published_date else ""
    ]
    
    content_string = "|".join(content_parts)
    return hashlib.sha256(content_string.encode('utf-8')).hexdigest()


def process_rss_item(item: RSSItem, feed_type: FeedType) -> ProcessedRSSItem:
    """
    Process RSS item with relevance analysis and keyword extraction.
    
    Args:
        item: RSS item to process
        feed_type: Type of RSS feed this item came from
        
    Returns:
        ProcessedRSSItem with analysis results
        
    MUST be deterministic.
    """
    if not item:
        raise ValueError("RSS item cannot be None")
        
    # Calculate relevance
    relevance_score = calculate_relevance_score(item)
    relevance = classify_content_relevance(relevance_score)
    
    # Extract analysis data
    content = f"{item.title} {item.description} {item.content or ''}"
    keywords = extract_keywords(content)
    regulatory_indicators = extract_regulatory_indicators(content)
    content_hash = generate_content_hash(item)
    
    return ProcessedRSSItem(
        rss_item=item,
        relevance=relevance,
        relevance_score=relevance_score,
        extracted_keywords=keywords,
        regulatory_indicators=regulatory_indicators,
        source_feed=feed_type,
        processed_at=datetime.utcnow(),
        content_hash=content_hash
    )


def filter_relevant_items(
    items: List[ProcessedRSSItem], 
    min_relevance: ContentRelevance = ContentRelevance.MEDIUM
) -> List[ProcessedRSSItem]:
    """
    Filter processed items by minimum relevance level.
    
    Args:
        items: List of processed RSS items
        min_relevance: Minimum relevance level to include
        
    Returns:
        Filtered list of relevant items
        
    MUST be deterministic.
    """
    if not items:
        return []
        
    relevance_order = {
        ContentRelevance.HIGH: 3,
        ContentRelevance.MEDIUM: 2, 
        ContentRelevance.LOW: 1,
        ContentRelevance.IGNORE: 0
    }
    
    min_score = relevance_order.get(min_relevance, 0)
    
    filtered = []
    for item in items:
        item_score = relevance_order.get(item.relevance, 0)
        if item_score >= min_score:
            filtered.append(item)
            
    # Sort by relevance score (descending) then by date (newest first)
    return sorted(filtered, 
                 key=lambda x: (x.relevance_score, 
                               x.rss_item.published_date or datetime.min),
                 reverse=True)


def deduplicate_items(items: List[ProcessedRSSItem]) -> List[ProcessedRSSItem]:
    """
    Remove duplicate items based on content hash.
    
    Args:
        items: List of processed RSS items
        
    Returns:
        List with duplicates removed
        
    MUST be deterministic.
    """
    if not items:
        return []
        
    seen_hashes = set()
    unique_items = []
    
    for item in items:
        if item.content_hash not in seen_hashes:
            seen_hashes.add(item.content_hash)
            unique_items.append(item)
            
    return unique_items


def build_fallback_metrics(
    processed_items: List[ProcessedRSSItem],
    processing_start: datetime,
    processing_end: datetime,
    errors: List[str] = None
) -> FallbackMetrics:
    """
    Build metrics summary for RSS fallback processing.
    
    Args:
        processed_items: List of processed items
        processing_start: Start time of processing
        processing_end: End time of processing
        errors: List of errors encountered
        
    Returns:
        FallbackMetrics summary
        
    MUST be deterministic.
    """
    if errors is None:
        errors = []
        
    high_relevance_count = sum(1 for item in processed_items 
                              if item.relevance == ContentRelevance.HIGH)
                              
    processing_time_ms = int(
        (processing_end - processing_start).total_seconds() * 1000
    )
    
    return FallbackMetrics(
        total_feeds_processed=1,  # Caller should aggregate
        total_items_found=len(processed_items),
        high_relevance_items=high_relevance_count,
        processing_time_ms=processing_time_ms,
        cache_hit_rate=0.0,  # Set by cache layer
        errors_encountered=len(errors),
        last_successful_update=processing_end if not errors else None
    )