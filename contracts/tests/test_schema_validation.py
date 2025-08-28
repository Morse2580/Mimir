"""
Test JSON Schema validation for RegOps contracts.

Ensures all schemas are valid and validation middleware works correctly.
"""

import json
import pytest
from pathlib import Path
from typing import Dict, Any

from contracts.validation import (
    ContractValidator,
    SchemaValidationError,
    validate_incident_input,
    validate_classification_result,
)


class TestSchemaValidation:
    """Test schema validation functionality."""

    @pytest.fixture
    def validator(self):
        """Create validator instance for testing."""
        return ContractValidator()

    @pytest.fixture
    def valid_incident_input(self) -> Dict[str, Any]:
        """Valid incident input data."""
        return {
            "incident_id": "INC-2024-001",
            "clients_affected": 1500,
            "downtime_minutes": 120,
            "services_critical": ["payment", "trading"],
            "detected_at": "2024-03-15T08:30:00Z",
            "confirmed_at": "2024-03-15T08:35:00Z",
            "occurred_at": "2024-03-15T08:25:00Z",
            "reputational_impact": "medium",
            "data_losses": False,
            "economic_impact_eur": 25000.50,
            "geographical_spread": "national",
        }

    @pytest.fixture
    def valid_classification_result(self) -> Dict[str, Any]:
        """Valid classification result data."""
        return {
            "incident_id": "INC-2024-001",
            "severity": "major",
            "anchor_timestamp": "2024-03-15T08:30:00Z",
            "anchor_source": "detected_at",
            "classification_reasons": [
                "clients_affected >= 1000",
                "critical services affected: payment, trading",
            ],
            "deadlines": {
                "incident_id": "INC-2024-001",
                "severity": "major",
                "anchor_time_utc": "2024-03-15T08:30:00Z",
                "anchor_time_brussels": "2024-03-15T09:30:00+01:00",
                "initial_notification": "2024-03-15T12:30:00Z",
                "intermediate_report": None,
                "final_report": "2024-03-22T08:30:00Z",
                "nbb_notification": "2024-03-15T12:30:00Z",
                "dst_transitions_handled": [],
                "calculation_confidence": 1.0,
                "timezone_used": "Europe/Brussels",
            },
            "requires_notification": True,
            "notification_deadline_hours": 4,
        }

    def test_validator_initialization(self, validator):
        """Test validator initializes correctly."""
        assert validator is not None
        assert len(validator._schema_cache) > 0

    def test_all_schemas_loaded(self, validator):
        """Test all expected schemas are loaded."""
        expected_schemas = [
            "incident_input.v1",
            "classification_result.v1",
            "review_request.v1",
            "review_decision.v1",
            "cost_event.v1",
            "pii_violation.v1",
            "onegate_export.v1",
        ]

        for schema_name in expected_schemas:
            assert schema_name in validator._schema_cache
            schema = validator.get_schema(schema_name)
            assert "$schema" in schema
            assert "title" in schema
            assert "type" in schema

    def test_incident_input_validation_valid(self, validator, valid_incident_input):
        """Test valid incident input passes validation."""
        # Should not raise exception
        validator.validate(valid_incident_input, "incident_input.v1")

    def test_incident_input_validation_invalid(self, validator):
        """Test invalid incident input fails validation."""
        invalid_data = {
            "incident_id": "",  # Invalid: empty string
            "clients_affected": -1,  # Invalid: negative
            "downtime_minutes": "not_a_number",  # Invalid: not integer
            "services_critical": [],  # Valid: empty array allowed
        }

        with pytest.raises(SchemaValidationError) as exc_info:
            validator.validate(invalid_data, "incident_input.v1")

        assert exc_info.value.schema_name == "incident_input.v1"

    def test_classification_result_validation_valid(
        self, validator, valid_classification_result
    ):
        """Test valid classification result passes validation."""
        validator.validate(valid_classification_result, "classification_result.v1")

    def test_classification_result_validation_invalid(self, validator):
        """Test invalid classification result fails validation."""
        invalid_data = {
            "incident_id": "INC-2024-001",
            "severity": "invalid_severity",  # Invalid enum value
            "anchor_timestamp": "not-a-timestamp",  # Invalid format
            "anchor_source": "invalid_source",  # Invalid enum
            "classification_reasons": [],  # Invalid: empty array
            "deadlines": {},  # Invalid: missing required fields
            "requires_notification": "not_boolean",  # Invalid: not boolean
        }

        with pytest.raises(SchemaValidationError):
            validator.validate(invalid_data, "classification_result.v1")

    def test_review_request_validation(self, validator):
        """Test review request validation."""
        valid_data = {
            "id": "req_abc123def456",
            "mapping_id": "map_dora_art18",
            "mapping_version_hash": "a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456",
            "priority": "high",
            "submitted_at": "2024-03-15T10:30:00Z",
            "submitted_by": "analyst@company.com",
            "evidence_urls": [
                "https://snapshots.blob.core.windows.net/regulatory/fsma_dora_guidance_2024.pdf"
            ],
            "rationale": "DORA Article 18 requires specific incident reporting procedures.",
        }

        validator.validate(valid_data, "review_request.v1")

    def test_cost_event_validation(self, validator):
        """Test cost event validation."""
        valid_data = {
            "id": "cost_abc123def456",
            "tenant": "pilot_bank",
            "api_type": "search",
            "processor": "pro",
            "cost_eur": 0.005,
            "use_case": "regulatory_search",
            "timestamp": "2024-03-15T10:30:00Z",
            "request_id": "req_search_789",
            "metadata": {
                "request_size_bytes": 1024,
                "response_size_bytes": 8192,
                "processing_time_ms": 1500,
                "circuit_breaker_state": "closed",
            },
        }

        validator.validate(valid_data, "cost_event.v1")

    def test_pii_violation_validation(self, validator):
        """Test PII violation validation."""
        valid_data = {
            "violation_type": "email",
            "detected_patterns": ["***@company.com"],
            "risk_score": 0.8,
            "payload_size": 2048,
            "timestamp": "2024-03-15T10:30:00Z",
            "context": "parallel_search_request",
        }

        validator.validate(valid_data, "pii_violation.v1")

    def test_schema_validation_error_details(self, validator):
        """Test schema validation error contains useful details."""
        invalid_data = {"invalid": "data"}

        with pytest.raises(SchemaValidationError) as exc_info:
            validator.validate(invalid_data, "incident_input.v1")

        error = exc_info.value
        assert error.schema_name == "incident_input.v1"
        assert error.data_type == "data"
        assert len(error.errors) > 0

    def test_multiple_validation(self, validator, valid_incident_input):
        """Test validating multiple data items at once."""
        valid_cost = {
            "id": None,
            "tenant": "test",
            "api_type": "search",
            "processor": "base",
            "cost_eur": 0.001,
            "use_case": "regulatory_search",
            "timestamp": "2024-03-15T10:30:00Z",
        }

        data_schemas = {
            "incident": (valid_incident_input, "incident_input.v1"),
            "cost": (valid_cost, "cost_event.v1"),
        }

        # Should not raise exception
        validator.validate_multiple(data_schemas)

    def test_direct_validation_functions(
        self, valid_incident_input, valid_classification_result
    ):
        """Test direct validation functions work correctly."""
        # These should not raise exceptions
        validate_incident_input(valid_incident_input)
        validate_classification_result(valid_classification_result)

    def test_schema_examples_are_valid(self, validator):
        """Test that all schema examples are valid against their schemas."""
        schema_dir = Path(__file__).parent.parent / "schemas"

        for schema_file in schema_dir.glob("*.json"):
            with open(schema_file) as f:
                schema = json.load(f)

            schema_name = schema_file.stem
            examples = schema.get("examples", [])

            for i, example in enumerate(examples):
                try:
                    validator.validate(example, schema_name, f"example_{i}")
                except SchemaValidationError as e:
                    pytest.fail(
                        f"Schema {schema_name} example {i} failed validation: {e.errors}"
                    )

    def test_missing_schema_error(self, validator):
        """Test error when requesting non-existent schema."""
        with pytest.raises(ValueError, match="Schema not found"):
            validator.get_schema("nonexistent_schema")

    @pytest.mark.parametrize(
        "schema_name",
        [
            "incident_input.v1",
            "classification_result.v1",
            "review_request.v1",
            "review_decision.v1",
            "cost_event.v1",
            "pii_violation.v1",
            "onegate_export.v1",
        ],
    )
    def test_schema_structure(self, validator, schema_name):
        """Test each schema has required structure."""
        schema = validator.get_schema(schema_name)

        # All schemas should have these fields
        assert "$schema" in schema
        assert "$id" in schema
        assert "title" in schema
        assert "description" in schema
        assert "type" in schema
        assert schema["type"] == "object"

        # Should have properties and examples
        assert "properties" in schema
        assert "examples" in schema
        assert len(schema["examples"]) >= 1


class TestSchemaEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.fixture
    def validator(self):
        return ContractValidator()

    def test_incident_input_edge_cases(self, validator):
        """Test incident input edge cases."""
        # Minimum valid incident
        minimal_incident = {
            "incident_id": "I",
            "clients_affected": 0,
            "downtime_minutes": 0,
            "services_critical": [],
        }
        validator.validate(minimal_incident, "incident_input.v1")

        # Maximum values
        maximal_incident = {
            "incident_id": "I" * 100,  # Max length
            "clients_affected": 10000000,  # Max value
            "downtime_minutes": 43200,  # 30 days
            "services_critical": [
                "payment",
                "trading",
                "settlement",
                "clearing",
                "custody",
                "lending",
                "deposit",
                "insurance",
                "risk_management",
                "compliance",
                "reporting",
            ],
        }
        validator.validate(maximal_incident, "incident_input.v1")

    def test_cost_event_precision(self, validator):
        """Test cost event decimal precision."""
        # Should accept 3 decimal places
        cost_data = {
            "id": None,
            "tenant": "test",
            "api_type": "search",
            "processor": "base",
            "cost_eur": 0.001,  # Minimum precision
            "use_case": "regulatory_search",
            "timestamp": "2024-03-15T10:30:00Z",
        }
        validator.validate(cost_data, "cost_event.v1")

    def test_pii_violation_risk_scores(self, validator):
        """Test PII violation risk score boundaries."""
        # Minimum risk score
        low_risk = {
            "violation_type": "email",
            "detected_patterns": ["***@example.com"],
            "risk_score": 0.0,
            "payload_size": 1,
            "timestamp": "2024-03-15T10:30:00Z",
        }
        validator.validate(low_risk, "pii_violation.v1")

        # Maximum risk score
        high_risk = {
            "violation_type": "belgian_rrn",
            "detected_patterns": ["XX.XX.XX-XXX.XX"],
            "risk_score": 1.0,
            "payload_size": 1000000,  # Max size
            "timestamp": "2024-03-15T10:30:00Z",
        }
        validator.validate(high_risk, "pii_violation.v1")

    def test_onegate_export_complex_structure(self, validator):
        """Test OneGate export with complex nested data."""
        complex_export = {
            "export_id": "export_abc123def456",
            "institution_info": {
                "institution_code": "BANK001",
                "institution_name": "Test Bank",
                "contact_email": "compliance@test.be",
            },
            "incident_data": {
                "incident_id": "INC-2024-001",
                "clients_affected": 100,
                "downtime_minutes": 30,
                "services_critical": ["payment"],
                "detected_at": "2024-03-15T08:30:00Z",
                "confirmed_at": "2024-03-15T08:35:00Z",
                "occurred_at": "2024-03-15T08:25:00Z",
                "description": "Test incident for schema validation",
                "root_cause": "Database timeout",
                "remediation_actions": "Increased timeout settings",
            },
            "classification": {
                "severity": "minor",
                "anchor_timestamp": "2024-03-15T08:30:00Z",
                "classification_reasons": ["Low client impact"],
                "requires_notification": False,
                "dora_article_references": ["Article 18"],
            },
            "deadlines": {
                "initial_notification": "2024-03-15T12:30:00Z",
                "final_report": "2024-03-22T08:30:00Z",
                "timezone_used": "Europe/Brussels",
            },
            "evidence_package": {
                "evidence_items": [
                    {
                        "id": "evidence_abc123def456",
                        "type": "log_file",
                        "url": "https://snapshots.blob.core.windows.net/evidence/logs.json",
                        "hash": "a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456",
                        "description": "System logs during incident",
                        "created_at": "2024-03-15T08:30:00Z",
                    }
                ],
                "audit_trail": [
                    {
                        "timestamp": "2024-03-15T08:30:00Z",
                        "action": "incident_detected",
                        "actor": "monitoring_system",
                        "details": "Automated detection",
                    }
                ],
            },
            "export_metadata": {
                "generated_at": "2024-03-15T15:00:00Z",
                "generated_by": "mimir_export",
                "schema_version": "dora_v2.1",
                "xsd_validation_status": "valid",
                "mimir_version": "1.0.0",
                "export_format": "xml",
                "file_size_bytes": 51200,
            },
        }

        validator.validate(complex_export, "onegate_export.v1")
