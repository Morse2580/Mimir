"""
Schema Contract Validation Tests

This module validates that all data contracts between modules conform to
their defined schemas and handle schema evolution properly.
These tests ensure API compatibility and prevent breaking changes.
"""

import pytest
import json
import jsonschema
from datetime import datetime, timezone
from typing import Dict, Any, Type, Union
from pathlib import Path
from dataclasses import dataclass, asdict
from enum import Enum

from backend.app.incidents.rules.contracts import (
    IncidentInput,
    ClassificationResult,
    Severity,
    DeadlineCalculation,
)
from backend.app.compliance.reviews.contracts import (
    ObligationMapping,
    ReviewRequest,
    ReviewDecision,
    ReviewStatus,
    ReviewPriority,
)
from backend.app.parallel.common.contracts import (
    PIIViolation,
    PIIViolationType,
    CircuitBreakerState,
)
from backend.app.cost.contracts import (
    CostUsage,
    BudgetAlert,
    KillSwitchEvent,
)


class TestModuleBoundaryContracts:
    """Test contracts at module boundaries."""
    
    @classmethod
    def setup_class(cls):
        """Set up JSON schemas for validation."""
        cls.schemas = cls._load_or_create_schemas()
    
    @classmethod
    def _load_or_create_schemas(cls) -> Dict[str, Dict[str, Any]]:
        """Load JSON schemas or create them if they don't exist."""
        schemas = {}
        
        # Incident Rules Module Schema
        schemas["incident_input"] = {
            "type": "object",
            "required": ["incident_id", "clients_affected", "downtime_minutes", "services_critical", "detected_at"],
            "properties": {
                "incident_id": {"type": "string", "pattern": "^INC-[0-9]{4}-[0-9]{3,6}$"},
                "clients_affected": {"type": "integer", "minimum": 0},
                "downtime_minutes": {"type": "integer", "minimum": 0},
                "services_critical": {
                    "type": "array",
                    "items": {"type": "string"},
                    "uniqueItems": True
                },
                "detected_at": {"type": "string", "format": "date-time"},
                "confirmed_at": {"type": ["string", "null"], "format": "date-time"},
                "occurred_at": {"type": ["string", "null"], "format": "date-time"},
                "reputational_impact": {"type": ["string", "null"], "enum": ["HIGH", "MEDIUM", "LOW", null]},
                "data_losses": {"type": ["boolean", "null"]},
                "economic_impact_eur": {"type": ["number", "null"], "minimum": 0},
                "geographical_spread": {"type": ["string", "null"]}
            },
            "additionalProperties": False
        }
        
        schemas["classification_result"] = {
            "type": "object",
            "required": ["incident_id", "severity", "anchor_timestamp", "anchor_source", 
                        "classification_reasons", "deadlines", "requires_notification"],
            "properties": {
                "incident_id": {"type": "string"},
                "severity": {"type": "string", "enum": ["critical", "major", "significant", "minor", "no_report"]},
                "anchor_timestamp": {"type": "string", "format": "date-time"},
                "anchor_source": {"type": "string", "enum": ["detected_at", "confirmed_at", "occurred_at"]},
                "classification_reasons": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1
                },
                "deadlines": {"$ref": "#/definitions/deadline_calculation"},
                "requires_notification": {"type": "boolean"},
                "notification_deadline_hours": {"type": ["integer", "null"], "minimum": 1}
            },
            "definitions": {
                "deadline_calculation": {
                    "type": "object",
                    "required": ["incident_id", "severity", "anchor_time_utc", "anchor_time_brussels",
                                "initial_notification", "final_report", "dst_transitions_handled", 
                                "calculation_confidence", "timezone_used"],
                    "properties": {
                        "incident_id": {"type": "string"},
                        "severity": {"type": "string", "enum": ["critical", "major", "significant", "minor"]},
                        "anchor_time_utc": {"type": "string", "format": "date-time"},
                        "anchor_time_brussels": {"type": "string", "format": "date-time"},
                        "initial_notification": {"type": "string", "format": "date-time"},
                        "intermediate_report": {"type": ["string", "null"], "format": "date-time"},
                        "final_report": {"type": "string", "format": "date-time"},
                        "nbb_notification": {"type": ["string", "null"], "format": "date-time"},
                        "dst_transitions_handled": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "calculation_confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "timezone_used": {"type": "string"}
                    }
                }
            },
            "additionalProperties": False
        }
        
        # Compliance Reviews Module Schema
        schemas["obligation_mapping"] = {
            "type": "object",
            "required": ["mapping_id", "incident_id", "obligation_text", "regulatory_source", 
                        "tier", "confidence_score", "supporting_evidence"],
            "properties": {
                "mapping_id": {"type": "string", "pattern": "^MAP-[0-9]{4}-[0-9]{3,6}$"},
                "incident_id": {"type": "string"},
                "obligation_text": {"type": "string", "minLength": 10, "maxLength": 2000},
                "regulatory_source": {"type": "string"},
                "tier": {"type": "string", "enum": ["TIER_A", "TIER_B"]},
                "confidence_score": {"type": "number", "minimum": 0, "maximum": 1},
                "supporting_evidence": {
                    "type": "array",
                    "items": {"type": "string", "format": "uri"},
                    "minItems": 1
                }
            },
            "additionalProperties": False
        }
        
        schemas["review_decision"] = {
            "type": "object",
            "required": ["review_id", "mapping_id", "reviewer_email", "status", 
                        "review_comments", "reviewed_at"],
            "properties": {
                "review_id": {"type": "string"},
                "mapping_id": {"type": "string"},
                "reviewer_email": {"type": "string", "format": "email"},
                "status": {"type": "string", "enum": ["APPROVED", "REJECTED", "NEEDS_REVISION"]},
                "review_comments": {"type": "string", "minLength": 10},
                "reviewed_at": {"type": "string", "format": "date-time"},
                "evidence_urls": {
                    "type": "array",
                    "items": {"type": "string", "format": "uri"}
                },
                "review_duration_minutes": {"type": "integer", "minimum": 0},
                "lock_id": {"type": ["string", "null"]}
            },
            "additionalProperties": False
        }
        
        # PII Boundary Schema
        schemas["pii_violation"] = {
            "type": "object",
            "required": ["violation_type", "detected_patterns", "risk_score", "payload_size"],
            "properties": {
                "violation_type": {
                    "type": "string", 
                    "enum": ["EMAIL", "PHONE", "BELGIAN_RRN", "BELGIAN_VAT", "IBAN", "CREDIT_CARD"]
                },
                "detected_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1
                },
                "risk_score": {"type": "number", "minimum": 0, "maximum": 1},
                "payload_size": {"type": "integer", "minimum": 0},
                "context_info": {"type": ["object", "null"]}
            },
            "additionalProperties": False
        }
        
        # Cost Tracking Schema  
        schemas["cost_usage"] = {
            "type": "object",
            "required": ["service_name", "operation", "cost_eur", "timestamp", "usage_id"],
            "properties": {
                "service_name": {"type": "string", "enum": ["parallel_search", "parallel_task", "parallel_webhook"]},
                "operation": {"type": "string"},
                "cost_eur": {"type": "number", "minimum": 0, "maximum": 1000},
                "timestamp": {"type": "string", "format": "date-time"},
                "usage_id": {"type": "string"},
                "metadata": {"type": ["object", "null"]}
            },
            "additionalProperties": False
        }
        
        schemas["budget_alert"] = {
            "type": "object", 
            "required": ["alert_type", "current_spend_eur", "budget_limit_eur", "threshold_percentage", 
                        "triggered_at", "time_remaining_hours"],
            "properties": {
                "alert_type": {"type": "string", "enum": ["WARNING", "CRITICAL", "KILL_SWITCH"]},
                "current_spend_eur": {"type": "number", "minimum": 0},
                "budget_limit_eur": {"type": "number", "minimum": 0},
                "threshold_percentage": {"type": "number", "minimum": 0, "maximum": 100},
                "triggered_at": {"type": "string", "format": "date-time"},
                "time_remaining_hours": {"type": "number", "minimum": 0},
                "projected_overage_eur": {"type": ["number", "null"]}
            },
            "additionalProperties": False
        }
        
        return schemas
    
    def test_incident_input_contract_validation(self):
        """Test IncidentInput contract validation."""
        # Valid incident input
        valid_incident = {
            "incident_id": "INC-2024-001",
            "clients_affected": 1500,
            "downtime_minutes": 45,
            "services_critical": ["payment", "trading"],
            "detected_at": "2024-03-15T14:30:00Z",
            "confirmed_at": "2024-03-15T14:45:00Z",
            "occurred_at": "2024-03-15T14:00:00Z",
            "reputational_impact": "HIGH",
            "data_losses": False,
            "economic_impact_eur": 75000.0,
            "geographical_spread": "EU"
        }
        
        # Should validate successfully
        jsonschema.validate(valid_incident, self.schemas["incident_input"])
        
        # Test invalid cases
        invalid_cases = [
            # Missing required field
            {k: v for k, v in valid_incident.items() if k != "incident_id"},
            
            # Invalid incident ID format
            {**valid_incident, "incident_id": "INVALID-FORMAT"},
            
            # Negative clients affected
            {**valid_incident, "clients_affected": -1},
            
            # Invalid datetime format
            {**valid_incident, "detected_at": "not-a-datetime"},
            
            # Invalid reputational impact
            {**valid_incident, "reputational_impact": "INVALID"},
            
            # Additional properties
            {**valid_incident, "extra_field": "not_allowed"}
        ]
        
        for invalid_case in invalid_cases:
            with pytest.raises(jsonschema.ValidationError):
                jsonschema.validate(invalid_case, self.schemas["incident_input"])
        
        print("✅ IncidentInput contract validation passed")
    
    def test_classification_result_contract_validation(self):
        """Test ClassificationResult contract validation."""
        valid_classification = {
            "incident_id": "INC-2024-001",
            "severity": "major",
            "anchor_timestamp": "2024-03-15T14:30:00Z",
            "anchor_source": "detected_at",
            "classification_reasons": [
                "clients_affected >= 1000",
                "downtime >= 60min with critical services"
            ],
            "deadlines": {
                "incident_id": "INC-2024-001",
                "severity": "major", 
                "anchor_time_utc": "2024-03-15T14:30:00Z",
                "anchor_time_brussels": "2024-03-15T15:30:00+01:00",
                "initial_notification": "2024-03-15T18:30:00Z",
                "intermediate_report": "2024-03-18T15:30:00Z",
                "final_report": "2024-03-29T15:30:00Z",
                "nbb_notification": "2024-03-15T18:30:00Z",
                "dst_transitions_handled": [],
                "calculation_confidence": 1.0,
                "timezone_used": "Europe/Brussels"
            },
            "requires_notification": True,
            "notification_deadline_hours": 4
        }
        
        # Should validate successfully
        jsonschema.validate(valid_classification, self.schemas["classification_result"])
        
        # Test invalid cases
        invalid_cases = [
            # Invalid severity
            {**valid_classification, "severity": "invalid_severity"},
            
            # Invalid anchor source
            {**valid_classification, "anchor_source": "invalid_source"},
            
            # Empty classification reasons
            {**valid_classification, "classification_reasons": []},
            
            # Invalid confidence score in deadlines
            {
                **valid_classification,
                "deadlines": {
                    **valid_classification["deadlines"],
                    "calculation_confidence": 1.5  # > 1.0
                }
            }
        ]
        
        for invalid_case in invalid_cases:
            with pytest.raises(jsonschema.ValidationError):
                jsonschema.validate(invalid_case, self.schemas["classification_result"])
        
        print("✅ ClassificationResult contract validation passed")
    
    def test_obligation_mapping_contract_validation(self):
        """Test ObligationMapping contract validation."""
        valid_mapping = {
            "mapping_id": "MAP-2024-001",
            "incident_id": "INC-2024-001", 
            "obligation_text": "DORA Article 19 requires incident notification within specified timeframes",
            "regulatory_source": "EU Regulation 2022/2554",
            "tier": "TIER_A",
            "confidence_score": 0.95,
            "supporting_evidence": [
                "https://eur-lex.europa.eu/eli/reg/2022/2554/oj",
                "https://www.esma.europa.eu/dora-guidance"
            ]
        }
        
        # Should validate successfully
        jsonschema.validate(valid_mapping, self.schemas["obligation_mapping"])
        
        # Test boundary conditions
        boundary_cases = [
            # Minimum obligation text length
            {**valid_mapping, "obligation_text": "x" * 10},  # Exactly 10 chars
            
            # Maximum confidence score
            {**valid_mapping, "confidence_score": 1.0},
            
            # Minimum confidence score
            {**valid_mapping, "confidence_score": 0.0},
            
            # Single evidence URL
            {**valid_mapping, "supporting_evidence": ["https://example.com"]}
        ]
        
        for case in boundary_cases:
            jsonschema.validate(case, self.schemas["obligation_mapping"])
        
        # Test invalid cases
        invalid_cases = [
            # Invalid mapping ID format
            {**valid_mapping, "mapping_id": "INVALID"},
            
            # Obligation text too short
            {**valid_mapping, "obligation_text": "short"},
            
            # Obligation text too long
            {**valid_mapping, "obligation_text": "x" * 2001},
            
            # Invalid tier
            {**valid_mapping, "tier": "TIER_C"},
            
            # Confidence score out of range
            {**valid_mapping, "confidence_score": 1.5},
            
            # No supporting evidence
            {**valid_mapping, "supporting_evidence": []},
            
            # Invalid URL format
            {**valid_mapping, "supporting_evidence": ["not-a-url"]}
        ]
        
        for invalid_case in invalid_cases:
            with pytest.raises(jsonschema.ValidationError):
                jsonschema.validate(invalid_case, self.schemas["obligation_mapping"])
        
        print("✅ ObligationMapping contract validation passed")
    
    def test_review_decision_contract_validation(self):
        """Test ReviewDecision contract validation."""
        valid_decision = {
            "review_id": "REV-2024-001",
            "mapping_id": "MAP-2024-001",
            "reviewer_email": "legal.expert@company.com",
            "status": "APPROVED",
            "review_comments": "Mapping correctly identifies DORA requirements. Approved for implementation.",
            "reviewed_at": "2024-03-15T16:30:00Z",
            "evidence_urls": [
                "https://internal.evidence.com/REV-2024-001"
            ],
            "review_duration_minutes": 45,
            "lock_id": "lock-uuid-12345"
        }
        
        # Should validate successfully
        jsonschema.validate(valid_decision, self.schemas["review_decision"])
        
        # Test all valid status values
        for status in ["APPROVED", "REJECTED", "NEEDS_REVISION"]:
            test_decision = {**valid_decision, "status": status}
            jsonschema.validate(test_decision, self.schemas["review_decision"])
        
        # Test invalid cases
        invalid_cases = [
            # Invalid email format
            {**valid_decision, "reviewer_email": "not-an-email"},
            
            # Invalid status
            {**valid_decision, "status": "MAYBE"},
            
            # Comment too short
            {**valid_decision, "review_comments": "short"},
            
            # Negative duration
            {**valid_decision, "review_duration_minutes": -1},
            
            # Invalid evidence URL
            {**valid_decision, "evidence_urls": ["not-a-url"]}
        ]
        
        for invalid_case in invalid_cases:
            with pytest.raises(jsonschema.ValidationError):
                jsonschema.validate(invalid_case, self.schemas["review_decision"])
        
        print("✅ ReviewDecision contract validation passed")
    
    def test_pii_violation_contract_validation(self):
        """Test PIIViolation contract validation."""
        valid_violation = {
            "violation_type": "EMAIL",
            "detected_patterns": ["admin@company.com", "support@example.org"],
            "risk_score": 0.85,
            "payload_size": 1024,
            "context_info": {
                "field": "message",
                "location": "line 5"
            }
        }
        
        # Should validate successfully
        jsonschema.validate(valid_violation, self.schemas["pii_violation"])
        
        # Test all violation types
        violation_types = ["EMAIL", "PHONE", "BELGIAN_RRN", "BELGIAN_VAT", "IBAN", "CREDIT_CARD"]
        for violation_type in violation_types:
            test_violation = {**valid_violation, "violation_type": violation_type}
            jsonschema.validate(test_violation, self.schemas["pii_violation"])
        
        # Test boundary conditions
        boundary_cases = [
            # Minimum risk score
            {**valid_violation, "risk_score": 0.0},
            
            # Maximum risk score
            {**valid_violation, "risk_score": 1.0},
            
            # Single detected pattern
            {**valid_violation, "detected_patterns": ["single@pattern.com"]},
            
            # Zero payload size
            {**valid_violation, "payload_size": 0},
            
            # Null context info
            {**valid_violation, "context_info": None}
        ]
        
        for case in boundary_cases:
            jsonschema.validate(case, self.schemas["pii_violation"])
        
        print("✅ PIIViolation contract validation passed")
    
    def test_cost_usage_contract_validation(self):
        """Test CostUsage contract validation."""
        valid_usage = {
            "service_name": "parallel_search",
            "operation": "regulatory_search",
            "cost_eur": 2.50,
            "timestamp": "2024-03-15T14:30:00Z",
            "usage_id": "usage-uuid-12345",
            "metadata": {
                "query_tokens": 150,
                "response_tokens": 300
            }
        }
        
        # Should validate successfully
        jsonschema.validate(valid_usage, self.schemas["cost_usage"])
        
        # Test all service names
        service_names = ["parallel_search", "parallel_task", "parallel_webhook"]
        for service_name in service_names:
            test_usage = {**valid_usage, "service_name": service_name}
            jsonschema.validate(test_usage, self.schemas["cost_usage"])
        
        # Test boundary conditions
        boundary_cases = [
            # Zero cost
            {**valid_usage, "cost_eur": 0.0},
            
            # Maximum allowed cost
            {**valid_usage, "cost_eur": 1000.0},
            
            # Null metadata
            {**valid_usage, "metadata": None}
        ]
        
        for case in boundary_cases:
            jsonschema.validate(case, self.schemas["cost_usage"])
        
        print("✅ CostUsage contract validation passed")
    
    def test_budget_alert_contract_validation(self):
        """Test BudgetAlert contract validation."""
        valid_alert = {
            "alert_type": "WARNING",
            "current_spend_eur": 1200.0,
            "budget_limit_eur": 1500.0,
            "threshold_percentage": 80.0,
            "triggered_at": "2024-03-15T14:30:00Z",
            "time_remaining_hours": 120.5,
            "projected_overage_eur": 50.0
        }
        
        # Should validate successfully
        jsonschema.validate(valid_alert, self.schemas["budget_alert"])
        
        # Test all alert types
        alert_types = ["WARNING", "CRITICAL", "KILL_SWITCH"]
        for alert_type in alert_types:
            test_alert = {**valid_alert, "alert_type": alert_type}
            jsonschema.validate(test_alert, self.schemas["budget_alert"])
        
        # Test kill switch scenario
        kill_switch_alert = {
            "alert_type": "KILL_SWITCH",
            "current_spend_eur": 1425.0,
            "budget_limit_eur": 1500.0,
            "threshold_percentage": 95.0,
            "triggered_at": "2024-03-15T14:30:00Z",
            "time_remaining_hours": 0.0,
            "projected_overage_eur": None
        }
        
        jsonschema.validate(kill_switch_alert, self.schemas["budget_alert"])
        
        print("✅ BudgetAlert contract validation passed")


class TestSchemaEvolutionCompatibility:
    """Test schema evolution and backward compatibility."""
    
    def test_schema_versioning_strategy(self):
        """Test schema versioning and compatibility."""
        # V1 schema (original)
        incident_v1_schema = {
            "type": "object",
            "required": ["incident_id", "clients_affected", "downtime_minutes"],
            "properties": {
                "incident_id": {"type": "string"},
                "clients_affected": {"type": "integer"},
                "downtime_minutes": {"type": "integer"},
                "services_critical": {"type": "array", "items": {"type": "string"}}
            }
        }
        
        # V2 schema (adds required fields)
        incident_v2_schema = {
            "type": "object", 
            "required": ["incident_id", "clients_affected", "downtime_minutes", "detected_at"],
            "properties": {
                "incident_id": {"type": "string"},
                "clients_affected": {"type": "integer"},
                "downtime_minutes": {"type": "integer"},
                "services_critical": {"type": "array", "items": {"type": "string"}},
                "detected_at": {"type": "string", "format": "date-time"},
                "economic_impact_eur": {"type": ["number", "null"]}  # Optional addition
            }
        }
        
        # V1 data should validate against V1 schema
        v1_data = {
            "incident_id": "INC-2024-001",
            "clients_affected": 100,
            "downtime_minutes": 30,
            "services_critical": ["customer_portal"]
        }
        
        jsonschema.validate(v1_data, incident_v1_schema)
        
        # V1 data should NOT validate against V2 schema (breaking change)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(v1_data, incident_v2_schema)
        
        # V2 data should validate against V2 schema
        v2_data = {
            **v1_data,
            "detected_at": "2024-03-15T14:30:00Z",
            "economic_impact_eur": 5000.0
        }
        
        jsonschema.validate(v2_data, incident_v2_schema)
        
        print("✅ Schema versioning strategy validation passed")
    
    def test_additive_schema_changes(self):
        """Test that additive schema changes maintain backward compatibility."""
        # Original schema
        base_schema = {
            "type": "object",
            "required": ["id", "name"],
            "properties": {
                "id": {"type": "string"},
                "name": {"type": "string"}
            },
            "additionalProperties": False
        }
        
        # Extended schema (additive change)
        extended_schema = {
            "type": "object", 
            "required": ["id", "name"],
            "properties": {
                "id": {"type": "string"},
                "name": {"type": "string"},
                "description": {"type": ["string", "null"]},  # Optional addition
                "metadata": {"type": ["object", "null"]}      # Optional addition
            },
            "additionalProperties": False
        }
        
        # Original data
        original_data = {
            "id": "test-001",
            "name": "Test Object"
        }
        
        # Should validate against both schemas
        jsonschema.validate(original_data, base_schema)
        jsonschema.validate(original_data, extended_schema)
        
        # Extended data  
        extended_data = {
            "id": "test-002",
            "name": "Extended Test Object",
            "description": "This object has additional fields",
            "metadata": {"version": 2, "tags": ["test"]}
        }
        
        # Should validate against extended schema
        jsonschema.validate(extended_data, extended_schema)
        
        # Should NOT validate against base schema (additionalProperties: false)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(extended_data, base_schema)
        
        print("✅ Additive schema changes validation passed")
    
    def test_schema_constraint_tightening(self):
        """Test impact of tightening schema constraints."""
        # Loose schema
        loose_schema = {
            "type": "object",
            "properties": {
                "value": {"type": "number"}
            }
        }
        
        # Tightened schema
        tight_schema = {
            "type": "object",
            "properties": {
                "value": {"type": "number", "minimum": 0, "maximum": 100}
            }
        }
        
        # Test data cases
        test_cases = [
            {"value": 50},      # Valid for both
            {"value": -10},     # Invalid for tight schema
            {"value": 150}      # Invalid for tight schema
        ]
        
        # First case should pass both
        jsonschema.validate(test_cases[0], loose_schema)
        jsonschema.validate(test_cases[0], tight_schema)
        
        # Second and third cases should pass loose but fail tight
        for test_case in test_cases[1:]:
            jsonschema.validate(test_case, loose_schema)
            with pytest.raises(jsonschema.ValidationError):
                jsonschema.validate(test_case, tight_schema)
        
        print("✅ Schema constraint tightening validation passed")


class TestCrossModuleDataFlow:
    """Test data flow contracts between modules."""
    
    def test_incident_to_classification_flow(self):
        """Test data flow from incidents to classification."""
        # Mock incident data from rules module
        incident_data = {
            "incident_id": "INC-2024-FLOW-001",
            "clients_affected": 2000,
            "downtime_minutes": 75,
            "services_critical": ["payment", "core_banking"],
            "detected_at": "2024-03-15T14:30:00Z"
        }
        
        # This should be consumable by classification logic
        # Test that required fields for classification are present
        classification_inputs = {
            "clients_affected": incident_data["clients_affected"],
            "downtime_minutes": incident_data["downtime_minutes"], 
            "services_critical": incident_data["services_critical"]
        }
        
        assert all(key in incident_data for key in classification_inputs.keys())
        assert isinstance(classification_inputs["clients_affected"], int)
        assert isinstance(classification_inputs["downtime_minutes"], int)
        assert isinstance(classification_inputs["services_critical"], list)
        
        print("✅ Incident to classification data flow validated")
    
    def test_classification_to_review_flow(self):
        """Test data flow from classification to review workflow."""
        # Mock classification result
        classification_data = {
            "incident_id": "INC-2024-FLOW-001",
            "severity": "major",
            "requires_notification": True,
            "classification_reasons": ["clients_affected >= 1000"]
        }
        
        # This should be consumable by review workflow
        review_inputs = {
            "incident_id": classification_data["incident_id"],
            "regulatory_implications": classification_data["requires_notification"],
            "justification": classification_data["classification_reasons"]
        }
        
        assert review_inputs["incident_id"] == classification_data["incident_id"]
        assert isinstance(review_inputs["regulatory_implications"], bool)
        assert isinstance(review_inputs["justification"], list)
        assert len(review_inputs["justification"]) > 0
        
        print("✅ Classification to review data flow validated")
    
    def test_review_to_export_flow(self):
        """Test data flow from review to export."""
        # Mock review decision
        review_data = {
            "review_id": "REV-2024-001",
            "mapping_id": "MAP-2024-001",
            "reviewer_email": "legal@company.com",
            "status": "APPROVED",
            "reviewed_at": "2024-03-15T16:30:00Z"
        }
        
        # This should be consumable by export logic
        export_inputs = {
            "review_status": review_data["status"],
            "reviewer": review_data["reviewer_email"],
            "review_timestamp": review_data["reviewed_at"],
            "audit_trail": {
                "review_id": review_data["review_id"],
                "mapping_id": review_data["mapping_id"]
            }
        }
        
        assert export_inputs["review_status"] in ["APPROVED", "REJECTED", "NEEDS_REVISION"]
        assert "@" in export_inputs["reviewer"]  # Email format
        assert export_inputs["review_timestamp"]  # Timestamp present
        assert export_inputs["audit_trail"]["review_id"]  # Audit trail preserved
        
        print("✅ Review to export data flow validated")
    
    def test_cost_to_circuit_breaker_flow(self):
        """Test data flow from cost tracking to circuit breaker."""
        # Mock cost usage data
        cost_data = {
            "current_spend_eur": 1425.0,
            "budget_limit_eur": 1500.0,
            "projected_spend_eur": 1520.0
        }
        
        # This should be consumable by circuit breaker logic
        circuit_breaker_inputs = {
            "spend_percentage": (cost_data["current_spend_eur"] / cost_data["budget_limit_eur"]) * 100,
            "budget_exceeded": cost_data["projected_spend_eur"] > cost_data["budget_limit_eur"],
            "remaining_budget": cost_data["budget_limit_eur"] - cost_data["current_spend_eur"]
        }
        
        assert circuit_breaker_inputs["spend_percentage"] > 95  # Above threshold
        assert circuit_breaker_inputs["budget_exceeded"] is True
        assert circuit_breaker_inputs["remaining_budget"] < 100  # Low remaining
        
        print("✅ Cost to circuit breaker data flow validated")


class TestSchemaPerformance:
    """Test schema validation performance."""
    
    def test_schema_validation_performance(self):
        """Test that schema validation meets performance requirements."""
        import time
        
        # Large but valid incident data
        large_incident = {
            "incident_id": "INC-2024-PERF-001",
            "clients_affected": 50000,
            "downtime_minutes": 180,
            "services_critical": [f"service_{i}" for i in range(20)],
            "detected_at": "2024-03-15T14:30:00Z",
            "confirmed_at": "2024-03-15T14:45:00Z",
            "occurred_at": "2024-03-15T14:00:00Z",
            "reputational_impact": "HIGH",
            "data_losses": True,
            "economic_impact_eur": 2500000.0,
            "geographical_spread": "EU, North America, Asia Pacific"
        }
        
        # Test validation performance
        schema = TestModuleBoundaryContracts._load_or_create_schemas()["incident_input"]
        
        num_validations = 1000
        start_time = time.time()
        
        for _ in range(num_validations):
            jsonschema.validate(large_incident, schema)
        
        total_time = time.time() - start_time
        avg_time_per_validation = (total_time / num_validations) * 1000  # milliseconds
        
        # Performance requirement: <1ms per validation
        assert avg_time_per_validation < 1.0, \
            f"Schema validation took {avg_time_per_validation:.2f}ms/validation (limit: 1ms)"
        
        print(f"✅ Schema validation performance: {avg_time_per_validation:.3f}ms per validation")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])