"""
RSS Fallback System - Core Function Tests

Tests for pure functions in the RSS fallback system.
"""

import pytest
from datetime import datetime, timedelta
from typing import List

from ..core import (
    calculate_relevance_score,
    classify_content_relevance,
    extract_regulatory_indicators,
    extract_keywords,
    generate_content_hash,
    process_rss_item,
    filter_relevant_items,
    deduplicate_items
)
from ..contracts import (
    RSSItem,
    ProcessedRSSItem,
    ContentRelevance,
    FeedType
)


class TestRelevanceScoring:
    """Test relevance scoring for RSS content."""
    
    def test_high_relevance_dora_content(self):
        """DORA-related content should score high relevance."""
        item = RSSItem(
            title="New DORA Technical Standards Released",
            description="The European Commission published new technical standards for DORA compliance requiring ICT risk management frameworks.",
            link="https://example.com/dora",
            published_date=datetime.utcnow(),
            guid="dora-123"
        )
        
        score = calculate_relevance_score(item)
        relevance = classify_content_relevance(score)
        
        assert score >= 0.7
        assert relevance == ContentRelevance.HIGH
        
    def test_medium_relevance_guidance_content(self):
        """General guidance content should score medium relevance."""
        item = RSSItem(
            title="EBA Issues Guidance on Risk Management",
            description="The European Banking Authority provides updated guidance on operational risk management procedures for financial institutions.",
            link="https://example.com/guidance",
            published_date=datetime.utcnow(),
            guid="guidance-456"
        )
        
        score = calculate_relevance_score(item)
        relevance = classify_content_relevance(score)
        
        assert 0.4 <= score < 0.7
        assert relevance == ContentRelevance.MEDIUM
        
    def test_low_relevance_general_news(self):
        """General news should score low relevance."""
        item = RSSItem(
            title="Bank Announces New Branch Opening",
            description="Local bank announces plans to open new branch in downtown area to serve customers better.",
            link="https://example.com/branch", 
            published_date=datetime.utcnow(),
            guid="branch-789"
        )
        
        score = calculate_relevance_score(item)
        relevance = classify_content_relevance(score)
        
        assert score < 0.4
        assert relevance in [ContentRelevance.LOW, ContentRelevance.IGNORE]
        
    def test_ignore_irrelevant_content(self):
        """Completely irrelevant content should be ignored."""
        item = RSSItem(
            title="Weather Update for Brussels",
            description="Sunny skies expected this weekend with temperatures reaching 25 degrees.",
            link="https://example.com/weather",
            published_date=datetime.utcnow(),
            guid="weather-000"
        )
        
        score = calculate_relevance_score(item)
        relevance = classify_content_relevance(score)
        
        assert score < 0.2
        assert relevance == ContentRelevance.IGNORE
        
    def test_recent_content_bonus(self):
        """Recent content should get relevance bonus."""
        recent_item = RSSItem(
            title="FSMA regulatory update",
            description="New requirements for financial reporting",
            link="https://example.com/recent",
            published_date=datetime.utcnow(),  # Very recent
            guid="recent-123"
        )
        
        old_item = RSSItem(
            title="FSMA regulatory update", 
            description="New requirements for financial reporting",
            link="https://example.com/old",
            published_date=datetime.utcnow() - timedelta(days=30),  # Old
            guid="old-123"
        )
        
        recent_score = calculate_relevance_score(recent_item)
        old_score = calculate_relevance_score(old_item)
        
        assert recent_score > old_score
        
    def test_deterministic_scoring(self):
        """Relevance scoring must be deterministic."""
        item = RSSItem(
            title="NIS2 Directive Implementation Guidelines",
            description="Updated guidelines for implementing NIS2 directive requirements",
            link="https://example.com/nis2",
            published_date=datetime(2024, 3, 15, 10, 30, 0),
            guid="nis2-guidelines"
        )
        
        # Score same item multiple times
        scores = [calculate_relevance_score(item) for _ in range(5)]
        
        # All scores should be identical
        assert len(set(scores)) == 1
        assert all(score == scores[0] for score in scores)


class TestRegulatoryIndicators:
    """Test extraction of regulatory indicators."""
    
    def test_extract_dora_indicators(self):
        """Should extract DORA-related indicators."""
        content = "The new DORA regulation requires financial entities to implement ICT risk management frameworks and incident reporting procedures."
        
        indicators = extract_regulatory_indicators(content)
        
        assert "DORA" in indicators
        assert "Incident Reporting" in indicators
        assert "Ict Risk" in indicators or "ICT Risk" in indicators
        
    def test_extract_regulation_references(self):
        """Should extract specific regulation references."""
        content = "Regulation (EU) 2022/2554 on digital operational resilience and Directive 2016/1148 on NIS security requirements."
        
        indicators = extract_regulatory_indicators(content)
        
        # Should find regulation patterns
        regulation_refs = [ind for ind in indicators if "2022/2554" in ind or "2016/1148" in ind]
        assert len(regulation_refs) >= 1
        
    def test_extract_deadlines(self):
        """Should extract deadline information."""
        content = "Financial institutions must comply by 17 January 2025. The deadline for submission is 31/12/2024."
        
        indicators = extract_regulatory_indicators(content)
        
        deadline_indicators = [ind for ind in indicators if "Deadline" in ind]
        assert len(deadline_indicators) >= 1
        
    def test_deterministic_extraction(self):
        """Indicator extraction must be deterministic."""
        content = "GDPR compliance requires data protection measures and DORA regulation mandates operational resilience."
        
        # Extract multiple times
        results = [extract_regulatory_indicators(content) for _ in range(3)]
        
        # All results should be identical
        assert all(result == results[0] for result in results)
        
    def test_empty_content_handling(self):
        """Should handle empty or invalid content gracefully."""
        assert extract_regulatory_indicators("") == []
        assert extract_regulatory_indicators(None) == []
        assert extract_regulatory_indicators("   ") == []


class TestKeywordExtraction:
    """Test keyword extraction functionality."""
    
    def test_extract_relevant_keywords(self):
        """Should extract relevant keywords excluding stop words."""
        content = "The European Banking Authority published new guidelines on operational risk management for financial institutions."
        
        keywords = extract_keywords(content, max_keywords=5)
        
        assert len(keywords) <= 5
        assert "european" in keywords or "banking" in keywords
        assert "guidelines" in keywords or "operational" in keywords
        
        # Should not contain stop words
        stop_words = ["the", "on", "for", "and", "or"]
        for stop_word in stop_words:
            assert stop_word not in keywords
            
    def test_keyword_frequency_ordering(self):
        """Keywords should be ordered by frequency."""
        content = "risk risk risk management management compliance compliance compliance compliance"
        
        keywords = extract_keywords(content, max_keywords=3)
        
        # "compliance" appears 4 times, "risk" 3 times, "management" 2 times
        assert keywords[0] == "compliance"
        assert keywords[1] == "risk"
        assert keywords[2] == "management"
        
    def test_deterministic_extraction(self):
        """Keyword extraction must be deterministic."""
        content = "Basel III capital requirements and MiFID II investor protection measures"
        
        results = [extract_keywords(content, max_keywords=5) for _ in range(3)]
        
        assert all(result == results[0] for result in results)


class TestContentHashing:
    """Test content hashing for change detection."""
    
    def test_identical_items_same_hash(self):
        """Identical items should produce same hash."""
        item1 = RSSItem(
            title="Test Title",
            description="Test Description", 
            link="https://example.com/test",
            published_date=datetime(2024, 3, 15, 10, 30, 0),
            guid="test-123"
        )
        
        item2 = RSSItem(
            title="Test Title",
            description="Test Description",
            link="https://example.com/test", 
            published_date=datetime(2024, 3, 15, 10, 30, 0),
            guid="test-123"
        )
        
        hash1 = generate_content_hash(item1)
        hash2 = generate_content_hash(item2)
        
        assert hash1 == hash2
        
    def test_different_items_different_hash(self):
        """Different items should produce different hashes."""
        item1 = RSSItem(
            title="Test Title 1",
            description="Test Description 1",
            link="https://example.com/test1",
            published_date=datetime(2024, 3, 15, 10, 30, 0),
            guid="test-123"
        )
        
        item2 = RSSItem(
            title="Test Title 2", 
            description="Test Description 2",
            link="https://example.com/test2",
            published_date=datetime(2024, 3, 15, 10, 30, 0),
            guid="test-456"
        )
        
        hash1 = generate_content_hash(item1)
        hash2 = generate_content_hash(item2)
        
        assert hash1 != hash2
        
    def test_deterministic_hashing(self):
        """Hash generation must be deterministic."""
        item = RSSItem(
            title="Consistent Title",
            description="Consistent Description",
            link="https://example.com/consistent",
            published_date=datetime(2024, 3, 15, 10, 30, 0),
            guid="consistent-123"
        )
        
        hashes = [generate_content_hash(item) for _ in range(5)]
        
        assert len(set(hashes)) == 1  # All hashes should be identical


class TestItemProcessing:
    """Test RSS item processing functionality."""
    
    def test_process_high_relevance_item(self):
        """Should correctly process high-relevance item."""
        item = RSSItem(
            title="DORA Technical Standards Published",
            description="New technical standards for digital operational resilience in financial services",
            link="https://example.com/dora-standards",
            published_date=datetime.utcnow(),
            guid="dora-standards-2024"
        )
        
        processed = process_rss_item(item, FeedType.NBB_NEWS)
        
        assert processed.relevance == ContentRelevance.HIGH
        assert processed.relevance_score >= 0.7
        assert len(processed.extracted_keywords) > 0
        assert len(processed.regulatory_indicators) > 0
        assert processed.source_feed == FeedType.NBB_NEWS
        assert processed.content_hash is not None
        
    def test_deterministic_processing(self):
        """Item processing must be deterministic."""
        item = RSSItem(
            title="Basel III Updates",
            description="Updated capital requirements under Basel III framework",
            link="https://example.com/basel",
            published_date=datetime(2024, 3, 15, 10, 30, 0),
            guid="basel-update"
        )
        
        results = [process_rss_item(item, FeedType.FSMA_NEWS) for _ in range(3)]
        
        # All processing results should be identical
        assert all(r.relevance_score == results[0].relevance_score for r in results)
        assert all(r.content_hash == results[0].content_hash for r in results)
        assert all(r.extracted_keywords == results[0].extracted_keywords for r in results)


class TestItemFiltering:
    """Test filtering and deduplication functionality."""
    
    def test_filter_by_relevance(self):
        """Should filter items by minimum relevance level."""
        high_item = self._create_processed_item("High relevance", ContentRelevance.HIGH, 0.8)
        medium_item = self._create_processed_item("Medium relevance", ContentRelevance.MEDIUM, 0.5)
        low_item = self._create_processed_item("Low relevance", ContentRelevance.LOW, 0.3)
        ignore_item = self._create_processed_item("Ignore", ContentRelevance.IGNORE, 0.1)
        
        items = [high_item, medium_item, low_item, ignore_item]
        
        # Filter for medium and above
        filtered = filter_relevant_items(items, ContentRelevance.MEDIUM)
        
        assert len(filtered) == 2
        assert high_item in filtered
        assert medium_item in filtered
        assert low_item not in filtered
        assert ignore_item not in filtered
        
    def test_sort_by_relevance_and_date(self):
        """Should sort filtered items by relevance and date."""
        old_high = self._create_processed_item(
            "Old high", ContentRelevance.HIGH, 0.8, 
            datetime.utcnow() - timedelta(days=2)
        )
        new_high = self._create_processed_item(
            "New high", ContentRelevance.HIGH, 0.9,
            datetime.utcnow()
        )
        medium = self._create_processed_item(
            "Medium", ContentRelevance.MEDIUM, 0.5,
            datetime.utcnow() - timedelta(hours=1)
        )
        
        items = [old_high, medium, new_high]  # Unsorted order
        filtered = filter_relevant_items(items, ContentRelevance.MEDIUM)
        
        # Should be sorted by relevance score descending
        assert filtered[0] == new_high  # Highest score
        assert filtered[1] == old_high  # Second highest score
        assert filtered[2] == medium   # Lowest score
        
    def test_deduplicate_by_hash(self):
        """Should remove duplicate items based on content hash."""
        item1 = self._create_processed_item("Item 1", ContentRelevance.HIGH, 0.8)
        item2 = self._create_processed_item("Item 2", ContentRelevance.MEDIUM, 0.5)
        item1_dup = self._create_processed_item("Item 1", ContentRelevance.HIGH, 0.8)
        
        # Manually set same hash for duplicates
        item1_dup = ProcessedRSSItem(
            rss_item=item1_dup.rss_item,
            relevance=item1_dup.relevance,
            relevance_score=item1_dup.relevance_score,
            extracted_keywords=item1_dup.extracted_keywords,
            regulatory_indicators=item1_dup.regulatory_indicators,
            source_feed=item1_dup.source_feed,
            processed_at=item1_dup.processed_at,
            content_hash=item1.content_hash  # Same hash as item1
        )
        
        items = [item1, item2, item1_dup]
        deduplicated = deduplicate_items(items)
        
        assert len(deduplicated) == 2
        assert item1 in deduplicated
        assert item2 in deduplicated
        # item1_dup should be removed as duplicate
        
    def _create_processed_item(
        self, 
        title: str, 
        relevance: ContentRelevance, 
        score: float,
        pub_date: datetime = None
    ) -> ProcessedRSSItem:
        """Helper to create ProcessedRSSItem for testing."""
        if pub_date is None:
            pub_date = datetime.utcnow()
            
        rss_item = RSSItem(
            title=title,
            description=f"Description for {title}",
            link=f"https://example.com/{title.lower().replace(' ', '-')}",
            published_date=pub_date,
            guid=f"guid-{title.lower().replace(' ', '-')}"
        )
        
        return ProcessedRSSItem(
            rss_item=rss_item,
            relevance=relevance,
            relevance_score=score,
            extracted_keywords=["keyword1", "keyword2"],
            regulatory_indicators=["indicator1"],
            source_feed=FeedType.NBB_NEWS,
            processed_at=datetime.utcnow(),
            content_hash=generate_content_hash(rss_item)
        )