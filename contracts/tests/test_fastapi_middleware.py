"""
Test FastAPI validation middleware integration.

Tests decorators and middleware functionality with FastAPI endpoints.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from typing import Dict, Any

from contracts.validation import (
    validate_request_schema,
    validate_response_schema,
    validate_contracts,
    schema_validation_exception_handler,
    SchemaValidationError,
)


@pytest.fixture
def app():
    """Create FastAPI test application."""
    app = FastAPI()

    # Add exception handler
    app.add_exception_handler(
        SchemaValidationError, schema_validation_exception_handler
    )

    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


class TestFastAPIValidationMiddleware:
    """Test FastAPI validation middleware."""

    def test_request_validation_success(self, app, client):
        """Test successful request validation."""

        @app.post("/test/incident")
        @validate_request_schema("incident_input.v1")
        async def test_endpoint(data: Dict[str, Any]):
            return {"status": "success", "incident_id": data["incident_id"]}

        valid_data = {
            "incident_id": "INC-2024-001",
            "clients_affected": 100,
            "downtime_minutes": 30,
            "services_critical": ["payment"],
        }

        response = client.post("/test/incident", json=valid_data)
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_request_validation_failure(self, app, client):
        """Test request validation failure."""

        @app.post("/test/incident")
        @validate_request_schema("incident_input.v1")
        async def test_endpoint(data: Dict[str, Any]):
            return {"status": "success"}

        invalid_data = {
            "incident_id": "",  # Invalid: empty string
            "clients_affected": -1,  # Invalid: negative
            "downtime_minutes": "not_a_number",  # Invalid: not integer
            "services_critical": ["invalid_service"],  # Invalid enum
        }

        response = client.post("/test/incident", json=invalid_data)
        assert response.status_code == 400
        assert "request_validation_failed" in response.json()["detail"]["error"]

    def test_response_validation_success(self, app, client):
        """Test successful response validation."""

        @app.post("/test/classify")
        @validate_response_schema("classification_result.v1")
        async def test_endpoint():
            return {
                "incident_id": "INC-2024-001",
                "severity": "major",
                "anchor_timestamp": "2024-03-15T08:30:00Z",
                "anchor_source": "detected_at",
                "classification_reasons": ["Test reason"],
                "deadlines": {
                    "incident_id": "INC-2024-001",
                    "severity": "major",
                    "anchor_time_utc": "2024-03-15T08:30:00Z",
                    "anchor_time_brussels": "2024-03-15T09:30:00+01:00",
                    "initial_notification": "2024-03-15T12:30:00Z",
                    "intermediate_report": None,
                    "final_report": "2024-03-22T08:30:00Z",
                    "nbb_notification": None,
                    "dst_transitions_handled": [],
                    "calculation_confidence": 1.0,
                    "timezone_used": "Europe/Brussels",
                },
                "requires_notification": True,
                "notification_deadline_hours": 4,
            }

        response = client.post("/test/classify")
        assert response.status_code == 200

    def test_combined_validation_success(self, app, client):
        """Test combined request and response validation."""

        @app.post("/test/combined")
        @validate_contracts(
            request_schema="incident_input.v1",
            response_schema="classification_result.v1",
        )
        async def test_endpoint(data: Dict[str, Any]):
            return {
                "incident_id": data["incident_id"],
                "severity": "minor",
                "anchor_timestamp": "2024-03-15T08:30:00Z",
                "anchor_source": "detected_at",
                "classification_reasons": ["Low impact"],
                "deadlines": {
                    "incident_id": data["incident_id"],
                    "severity": "minor",
                    "anchor_time_utc": "2024-03-15T08:30:00Z",
                    "anchor_time_brussels": "2024-03-15T09:30:00+01:00",
                    "initial_notification": "2024-03-15T12:30:00Z",
                    "intermediate_report": None,
                    "final_report": "2024-03-22T08:30:00Z",
                    "nbb_notification": None,
                    "dst_transitions_handled": [],
                    "calculation_confidence": 1.0,
                    "timezone_used": "Europe/Brussels",
                },
                "requires_notification": False,
            }

        valid_input = {
            "incident_id": "INC-2024-TEST",
            "clients_affected": 10,
            "downtime_minutes": 5,
            "services_critical": [],
        }

        response = client.post("/test/combined", json=valid_input)
        assert response.status_code == 200
        result = response.json()
        assert result["incident_id"] == "INC-2024-TEST"

    def test_review_request_validation(self, app, client):
        """Test review request validation."""

        @app.post("/test/review")
        @validate_request_schema("review_request.v1")
        async def test_endpoint(data: Dict[str, Any]):
            return {"status": "submitted", "id": data["id"]}

        valid_data = {
            "id": "req_abc123def456",
            "mapping_id": "map_test",
            "mapping_version_hash": "a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456",
            "priority": "normal",
            "submitted_at": "2024-03-15T10:30:00Z",
            "submitted_by": "test@company.com",
            "evidence_urls": [
                "https://snapshots.blob.core.windows.net/regulatory/test.pdf"
            ],
            "rationale": "Test rationale for validation",
        }

        response = client.post("/test/review", json=valid_data)
        assert response.status_code == 200

    def test_cost_event_validation(self, app, client):
        """Test cost event validation."""

        @app.post("/test/cost")
        @validate_request_schema("cost_event.v1")
        async def test_endpoint(data: Dict[str, Any]):
            return {"recorded": True, "cost": data["cost_eur"]}

        valid_data = {
            "id": None,
            "tenant": "test_tenant",
            "api_type": "search",
            "processor": "base",
            "cost_eur": 0.005,
            "use_case": "regulatory_search",
            "timestamp": "2024-03-15T10:30:00Z",
        }

        response = client.post("/test/cost", json=valid_data)
        assert response.status_code == 200

    def test_pii_violation_validation(self, app, client):
        """Test PII violation validation."""

        @app.post("/test/pii")
        @validate_request_schema("pii_violation.v1")
        async def test_endpoint(data: Dict[str, Any]):
            return {"blocked": True, "violation_type": data["violation_type"]}

        valid_data = {
            "violation_type": "email",
            "detected_patterns": ["***@example.com"],
            "risk_score": 0.9,
            "payload_size": 1024,
            "timestamp": "2024-03-15T10:30:00Z",
            "context": "test_context",
        }

        response = client.post("/test/pii", json=valid_data)
        assert response.status_code == 200

    def test_validation_with_missing_data(self, app, client):
        """Test validation with missing required data."""

        @app.post("/test/missing")
        @validate_request_schema("incident_input.v1")
        async def test_endpoint(data: Dict[str, Any]):
            return {"status": "success"}

        incomplete_data = {
            "incident_id": "INC-2024-001"
            # Missing required fields
        }

        response = client.post("/test/missing", json=incomplete_data)
        assert response.status_code == 400
        error_detail = response.json()["detail"]
        assert error_detail["error"] == "request_validation_failed"
        assert error_detail["schema"] == "incident_input.v1"

    def test_validation_with_additional_properties(self, app, client):
        """Test validation with additional properties (should fail)."""

        @app.post("/test/additional")
        @validate_request_schema("incident_input.v1")
        async def test_endpoint(data: Dict[str, Any]):
            return {"status": "success"}

        data_with_extra = {
            "incident_id": "INC-2024-001",
            "clients_affected": 100,
            "downtime_minutes": 30,
            "services_critical": [],
            "unexpected_field": "should_fail",  # Not allowed by schema
        }

        response = client.post("/test/additional", json=data_with_extra)
        assert response.status_code == 400

    def test_endpoint_without_validation(self, app, client):
        """Test endpoint without validation works normally."""

        @app.post("/test/no-validation")
        async def test_endpoint(data: Dict[str, Any]):
            return {"received": data}

        any_data = {"anything": "goes", "no": "validation"}

        response = client.post("/test/no-validation", json=any_data)
        assert response.status_code == 200
        assert response.json()["received"] == any_data

    def test_validation_error_format(self, app, client):
        """Test validation error response format."""

        @app.post("/test/error-format")
        @validate_request_schema("incident_input.v1")
        async def test_endpoint(data: Dict[str, Any]):
            return {"status": "success"}

        invalid_data = {"invalid": "structure"}

        response = client.post("/test/error-format", json=invalid_data)
        assert response.status_code == 400

        error_response = response.json()
        assert "detail" in error_response
        detail = error_response["detail"]

        # Check error structure
        assert "error" in detail
        assert "schema" in detail
        assert "errors" in detail
        assert detail["error"] == "request_validation_failed"
        assert detail["schema"] == "incident_input.v1"
        assert isinstance(detail["errors"], list)

    def test_multiple_validation_decorators(self, app, client):
        """Test endpoint with multiple validation decorators."""

        @app.post("/test/multiple")
        @validate_response_schema("classification_result.v1")
        @validate_request_schema("incident_input.v1")
        async def test_endpoint(data: Dict[str, Any]):
            # Return valid classification result
            return {
                "incident_id": data["incident_id"],
                "severity": "minor",
                "anchor_timestamp": "2024-03-15T08:30:00Z",
                "anchor_source": "detected_at",
                "classification_reasons": ["Test classification"],
                "deadlines": {
                    "incident_id": data["incident_id"],
                    "severity": "minor",
                    "anchor_time_utc": "2024-03-15T08:30:00Z",
                    "anchor_time_brussels": "2024-03-15T09:30:00+01:00",
                    "initial_notification": "2024-03-15T12:30:00Z",
                    "intermediate_report": None,
                    "final_report": "2024-03-22T08:30:00Z",
                    "nbb_notification": None,
                    "dst_transitions_handled": [],
                    "calculation_confidence": 1.0,
                    "timezone_used": "Europe/Brussels",
                },
                "requires_notification": False,
            }

        valid_input = {
            "incident_id": "INC-2024-MULTI",
            "clients_affected": 5,
            "downtime_minutes": 2,
            "services_critical": [],
        }

        response = client.post("/test/multiple", json=valid_input)
        assert response.status_code == 200
