"""
JSON Schema validation middleware for FastAPI endpoints.

Validates all requests and responses against schema contracts to ensure
data integrity across the Belgian RegOps platform.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional, Callable
from functools import wraps

import jsonschema
from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse



class SchemaValidationError(Exception):
    """Raised when schema validation fails."""

    def __init__(self, schema_name: str, errors: list, data_type: str = "request"):
        self.schema_name = schema_name
        self.errors = errors
        self.data_type = data_type
        super().__init__(f"Schema validation failed for {schema_name} {data_type}")


class ContractValidator:
    """
    JSON Schema validator for RegOps platform contracts.

    Loads and caches schemas, validates requests/responses against contracts.
    """

    def __init__(self, schema_dir: Optional[Path] = None):
        """Initialize validator with schema directory."""
        if schema_dir is None:
            schema_dir = Path(__file__).parent / "schemas"

        self.schema_dir = schema_dir
        self._schema_cache: Dict[str, Dict[str, Any]] = {}
        self._load_schemas()

    def _load_schemas(self) -> None:
        """Load all JSON schemas from the schemas directory."""
        if not self.schema_dir.exists():
            raise FileNotFoundError(f"Schema directory not found: {self.schema_dir}")

        for schema_file in self.schema_dir.glob("*.json"):
            try:
                with open(schema_file, "r", encoding="utf-8") as f:
                    schema = json.load(f)

                schema_name = schema_file.stem
                self._schema_cache[schema_name] = schema

            except (json.JSONDecodeError, IOError) as e:
                raise ValueError(f"Failed to load schema {schema_file}: {e}")

    def get_schema(self, schema_name: str) -> Dict[str, Any]:
        """Get schema by name."""
        if schema_name not in self._schema_cache:
            raise ValueError(f"Schema not found: {schema_name}")
        return self._schema_cache[schema_name]

    def validate(self, data: Any, schema_name: str, data_type: str = "data") -> None:
        """
        Validate data against named schema.

        Args:
            data: Data to validate
            schema_name: Name of schema (without .json extension)
            data_type: Type of data for error messages

        Raises:
            SchemaValidationError: If validation fails
        """
        try:
            schema = self.get_schema(schema_name)
            jsonschema.validate(instance=data, schema=schema)

        except jsonschema.ValidationError as e:
            errors = [str(e)]
            raise SchemaValidationError(schema_name, errors, data_type)
        except jsonschema.SchemaError as e:
            raise ValueError(f"Invalid schema {schema_name}: {e}")

    def validate_multiple(self, data_schemas: Dict[str, tuple[Any, str]]) -> None:
        """
        Validate multiple data items against their schemas.

        Args:
            data_schemas: Dict mapping data_type to (data, schema_name) tuples

        Raises:
            SchemaValidationError: If any validation fails
        """
        for data_type, (data, schema_name) in data_schemas.items():
            self.validate(data, schema_name, data_type)


# Global validator instance
_validator: Optional[ContractValidator] = None


def get_validator() -> ContractValidator:
    """Get or create global validator instance."""
    global _validator
    if _validator is None:
        _validator = ContractValidator()
    return _validator


def validate_request_schema(schema_name: str):
    """
    Decorator to validate FastAPI request body against schema.

    Args:
        schema_name: Name of JSON schema file (without .json extension)

    Example:
        @app.post("/incidents/classify")
        @validate_request_schema("incident_input.v1")
        async def classify_incident(request_data: dict):
            return await classify(request_data)
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            # Extract request data from function arguments
            request_data = None

            # Look for request data in kwargs or args
            for arg in args:
                if isinstance(arg, dict) and not isinstance(arg, Request):
                    request_data = arg
                    break

            if request_data is None:
                for key, value in kwargs.items():
                    if isinstance(value, dict) and key != "request":
                        request_data = value
                        break

            if request_data is not None:
                try:
                    validator = get_validator()
                    validator.validate(request_data, schema_name, "request")
                except SchemaValidationError as e:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "error": "request_validation_failed",
                            "schema": e.schema_name,
                            "errors": e.errors,
                        },
                    )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def validate_response_schema(schema_name: str):
    """
    Decorator to validate FastAPI response against schema.

    Args:
        schema_name: Name of JSON schema file (without .json extension)

    Example:
        @app.post("/incidents/classify")
        @validate_response_schema("classification_result.v1")
        async def classify_incident(data: dict):
            return await classify(data)
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            result = await func(*args, **kwargs)

            # Extract JSON data from response
            response_data = result
            if isinstance(result, Response):
                if hasattr(result, "body"):
                    try:
                        response_data = json.loads(result.body)
                    except (json.JSONDecodeError, AttributeError):
                        response_data = result.body

            if isinstance(response_data, dict):
                try:
                    validator = get_validator()
                    validator.validate(response_data, schema_name, "response")
                except SchemaValidationError as e:
                    # Log the validation error but don't block response
                    print(f"Response validation failed: {e}")
                    # In development, you might want to raise the error
                    # raise HTTPException(500, detail="response_validation_failed")

            return result

        return wrapper

    return decorator


def validate_contracts(
    request_schema: Optional[str] = None, response_schema: Optional[str] = None
):
    """
    Combined decorator for request and response validation.

    Args:
        request_schema: Name of request schema (without .json)
        response_schema: Name of response schema (without .json)

    Example:
        @app.post("/incidents/classify")
        @validate_contracts(
            request_schema="incident_input.v1",
            response_schema="classification_result.v1"
        )
        async def classify_incident(data: dict):
            return await classify(data)
    """

    def decorator(func: Callable) -> Callable:
        # Apply response validation first (outer)
        if response_schema:
            func = validate_response_schema(response_schema)(func)

        # Apply request validation second (inner)
        if request_schema:
            func = validate_request_schema(request_schema)(func)

        return func

    return decorator


# Schema-specific validators for common operations
def validate_incident_input(data: Dict[str, Any]) -> None:
    """Validate incident input data."""
    validator = get_validator()
    validator.validate(data, "incident_input.v1", "incident_input")


def validate_classification_result(data: Dict[str, Any]) -> None:
    """Validate classification result data."""
    validator = get_validator()
    validator.validate(data, "classification_result.v1", "classification_result")


def validate_review_request(data: Dict[str, Any]) -> None:
    """Validate review request data."""
    validator = get_validator()
    validator.validate(data, "review_request.v1", "review_request")


def validate_review_decision(data: Dict[str, Any]) -> None:
    """Validate review decision data."""
    validator = get_validator()
    validator.validate(data, "review_decision.v1", "review_decision")


def validate_cost_event(data: Dict[str, Any]) -> None:
    """Validate cost event data."""
    validator = get_validator()
    validator.validate(data, "cost_event.v1", "cost_event")


def validate_pii_violation(data: Dict[str, Any]) -> None:
    """Validate PII violation data."""
    validator = get_validator()
    validator.validate(data, "pii_violation.v1", "pii_violation")


def validate_onegate_export(data: Dict[str, Any]) -> None:
    """Validate OneGate export data."""
    validator = get_validator()
    validator.validate(data, "onegate_export.v1", "onegate_export")


# Error handler for schema validation errors
async def schema_validation_exception_handler(
    request: Request, exc: SchemaValidationError
) -> JSONResponse:
    """FastAPI exception handler for schema validation errors."""
    return JSONResponse(
        status_code=400,
        content={
            "error": "schema_validation_failed",
            "schema": exc.schema_name,
            "data_type": exc.data_type,
            "errors": exc.errors,
            "timestamp": "2024-03-15T10:30:00Z",  # Use actual timestamp
        },
    )
