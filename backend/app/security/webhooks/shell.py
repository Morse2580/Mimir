import json
import time
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import redis
from .contracts import (
    WebhookConfig, WebhookHeaders, WebhookPayload, WebhookValidationResult,
    WebhookStatus, WebhookSource, ReplayEntry, WebhookValidationError,
    InvalidSignatureError, TimestampInvalidError, ReplayDetectedError,
    PayloadTooLargeError, RateLimitExceededError
)
from .core import (
    verify_hmac_signature, validate_timestamp, validate_payload_size,
    create_replay_entry, calculate_rate_limit_key, sanitize_webhook_data,
    calculate_validation_metrics, is_suspicious_payload, validate_content_type
)


logger = logging.getLogger(__name__)


class WebhookValidator:
    def __init__(
        self,
        config: WebhookConfig,
        redis_client: Optional[redis.Redis] = None
    ):
        self.config = config
        self.redis_client = redis_client
        self._rate_limit_cache: Dict[str, tuple[int, float]] = {}
    
    async def validate_webhook(
        self,
        raw_body: bytes,
        headers: WebhookHeaders,
        source: WebhookSource
    ) -> WebhookValidationResult:
        start_time = time.time()
        validation_steps = 0
        
        try:
            validation_steps += 1
            self._validate_payload_size(len(raw_body))
            
            validation_steps += 1
            self._validate_content_type(headers.content_type)
            
            validation_steps += 1
            await self._validate_rate_limit(headers.source_ip, headers.user_agent)
            
            validation_steps += 1
            self._validate_timestamp(headers.timestamp)
            
            validation_steps += 1
            self._validate_signature(raw_body, headers.signature)
            
            validation_steps += 1
            await self._check_replay_protection(raw_body, headers)
            
            parsed_data = self._parse_payload(raw_body)
            
            validation_steps += 1
            self._validate_payload_content(parsed_data)
            
            payload = WebhookPayload(
                raw_body=raw_body,
                parsed_data=parsed_data,
                headers=headers,
                received_at=datetime.now(timezone.utc)
            )
            
            metrics = calculate_validation_metrics(start_time, len(raw_body), validation_steps)
            
            logger.info(
                f"Webhook validated successfully from {source.value}",
                extra={
                    "source": source.value,
                    "payload_size": len(raw_body),
                    "validation_time_ms": metrics["duration_ms"],
                    "source_ip": headers.source_ip
                }
            )
            
            return WebhookValidationResult(
                status=WebhookStatus.VERIFIED,
                payload=payload,
                error_message=None,
                validation_time_ms=metrics["duration_ms"],
                source=source
            )
            
        except WebhookValidationError as e:
            metrics = calculate_validation_metrics(start_time, len(raw_body), validation_steps)
            
            logger.warning(
                f"Webhook validation failed: {e.message}",
                extra={
                    "source": source.value,
                    "status": e.status.value,
                    "error": e.message,
                    "payload_size": len(raw_body),
                    "validation_time_ms": metrics["duration_ms"],
                    "source_ip": headers.source_ip
                }
            )
            
            return WebhookValidationResult(
                status=e.status,
                payload=None,
                error_message=e.message,
                validation_time_ms=metrics["duration_ms"],
                source=source
            )
        
        except Exception as e:
            metrics = calculate_validation_metrics(start_time, len(raw_body), validation_steps)
            
            logger.error(
                f"Unexpected error during webhook validation: {str(e)}",
                extra={
                    "source": source.value,
                    "error": str(e),
                    "payload_size": len(raw_body),
                    "validation_time_ms": metrics["duration_ms"],
                    "source_ip": headers.source_ip
                },
                exc_info=True
            )
            
            return WebhookValidationResult(
                status=WebhookStatus.INVALID_SIGNATURE,
                payload=None,
                error_message="Internal validation error",
                validation_time_ms=metrics["duration_ms"],
                source=source
            )
    
    def _validate_payload_size(self, size: int):
        if not validate_payload_size(size, self.config.max_payload_size):
            raise PayloadTooLargeError(
                f"Payload size {size} exceeds limit {self.config.max_payload_size}"
            )
    
    def _validate_content_type(self, content_type: Optional[str]):
        if not validate_content_type(content_type):
            raise WebhookValidationError(
                WebhookStatus.INVALID_SIGNATURE,
                f"Invalid content type: {content_type}"
            )
    
    async def _validate_rate_limit(self, source_ip: Optional[str], user_agent: Optional[str]):
        rate_key = calculate_rate_limit_key(source_ip, user_agent)
        current_time = time.time()
        
        if self.redis_client:
            try:
                pipeline = self.redis_client.pipeline()
                window_key = f"{rate_key}:{int(current_time // 60)}"
                
                pipeline.incr(window_key)
                pipeline.expire(window_key, 120)  # Keep for 2 minutes
                
                results = pipeline.execute()
                current_count = results[0]
                
                if current_count > self.config.rate_limit_per_minute:
                    raise RateLimitExceededError(
                        f"Rate limit exceeded: {current_count} requests in current minute"
                    )
                
            except redis.RedisError:
                pass  # Fall back to in-memory rate limiting
        
        if rate_key in self._rate_limit_cache:
            count, window_start = self._rate_limit_cache[rate_key]
            
            if current_time - window_start < 60:
                if count >= self.config.rate_limit_per_minute:
                    raise RateLimitExceededError(
                        f"Rate limit exceeded: {count} requests in current minute"
                    )
                self._rate_limit_cache[rate_key] = (count + 1, window_start)
            else:
                self._rate_limit_cache[rate_key] = (1, current_time)
        else:
            self._rate_limit_cache[rate_key] = (1, current_time)
    
    def _validate_timestamp(self, timestamp: Optional[str]):
        if not validate_timestamp(timestamp, self.config.timestamp_tolerance_seconds):
            raise TimestampInvalidError(
                f"Timestamp {timestamp} is invalid or outside tolerance window"
            )
    
    def _validate_signature(self, payload: bytes, signature: Optional[str]):
        if not signature:
            raise InvalidSignatureError("Missing signature header")
        
        if not verify_hmac_signature(payload, signature, self.config.secret_key, self.config.algorithm):
            raise InvalidSignatureError("Signature verification failed")
    
    async def _check_replay_protection(self, payload: bytes, headers: WebhookHeaders):
        if not headers.signature or not headers.timestamp:
            return  # Already validated in previous steps
        
        replay_entry = create_replay_entry(
            payload,
            headers.signature,
            headers.timestamp,
            headers.source_ip
        )
        
        cache_key = replay_entry.cache_key()
        
        if self.redis_client:
            try:
                if self.redis_client.exists(cache_key):
                    raise ReplayDetectedError(
                        f"Duplicate request detected: {replay_entry.request_id}"
                    )
                
                self.redis_client.setex(
                    cache_key,
                    self.config.replay_cache_ttl,
                    json.dumps({
                        "request_id": replay_entry.request_id,
                        "timestamp": replay_entry.timestamp.isoformat(),
                        "source_ip": replay_entry.source_ip
                    })
                )
                
            except redis.RedisError as e:
                logger.warning(f"Redis error during replay check: {e}")
    
    def _parse_payload(self, raw_body: bytes) -> Dict[str, Any]:
        try:
            if not raw_body:
                return {}
            
            content = raw_body.decode('utf-8')
            
            if content.startswith('{') or content.startswith('['):
                return json.loads(content)
            
            return {"raw_content": content}
            
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to parse webhook payload: {e}")
            return {"raw_body": raw_body.hex()}
    
    def _validate_payload_content(self, parsed_data: Dict[str, Any]):
        if is_suspicious_payload(parsed_data):
            raise WebhookValidationError(
                WebhookStatus.INVALID_SIGNATURE,
                "Payload contains suspicious content"
            )
        
        sanitized_data = sanitize_webhook_data(parsed_data)
        if len(str(sanitized_data)) > self.config.max_payload_size // 2:
            logger.warning("Payload is unusually large after sanitization")


class WebhookSecurityService:
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis_client = redis_client
        self._validators: Dict[WebhookSource, WebhookValidator] = {}
    
    def register_source(self, source: WebhookSource, config: WebhookConfig):
        validator = WebhookValidator(config, self.redis_client)
        self._validators[source] = validator
        
        logger.info(
            f"Registered webhook validator for {source.value}",
            extra={"source": source.value, "max_payload": config.max_payload_size}
        )
    
    async def validate_webhook(
        self,
        source: WebhookSource,
        raw_body: bytes,
        headers: Dict[str, str]
    ) -> WebhookValidationResult:
        if source not in self._validators:
            logger.error(f"No validator registered for source: {source.value}")
            return WebhookValidationResult(
                status=WebhookStatus.INVALID_SIGNATURE,
                payload=None,
                error_message=f"Unknown webhook source: {source.value}",
                validation_time_ms=0,
                source=source
            )
        
        webhook_headers = WebhookHeaders.from_dict(headers)
        validator = self._validators[source]
        
        return await validator.validate_webhook(raw_body, webhook_headers, source)
    
    def get_security_metrics(self) -> Dict[str, Any]:
        total_sources = len(self._validators)
        
        return {
            "registered_sources": total_sources,
            "sources": [source.value for source in self._validators.keys()],
            "cache_backend": "redis" if self.redis_client else "memory",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }