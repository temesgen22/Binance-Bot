"""
Correlation ID management for distributed tracing.

Correlation IDs allow tracking requests across services and async operations.
"""
from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger

# Context variable for correlation ID (thread-safe and async-safe)
correlation_id_var: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


def get_correlation_id() -> Optional[str]:
    """Get the current correlation ID from context."""
    return correlation_id_var.get()


def set_correlation_id(correlation_id: str) -> None:
    """Set the correlation ID in the current context."""
    correlation_id_var.set(correlation_id)


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Middleware to add correlation IDs to requests.
    
    Extracts correlation ID from X-Correlation-ID header, or generates a new one.
    Adds correlation ID to response headers and log context.
    """
    
    async def dispatch(self, request: Request, call_next):
        # Get correlation ID from header, or generate new one
        correlation_id = request.headers.get("X-Correlation-ID")
        if not correlation_id:
            correlation_id = str(uuid.uuid4())
        
        # Set in context for this request
        set_correlation_id(correlation_id)
        
        # Bind correlation ID to logger context
        logger.configure(extra={"correlation_id": correlation_id})
        
        # Process request
        response = await call_next(request)
        
        # Add correlation ID to response headers
        response.headers["X-Correlation-ID"] = correlation_id
        
        return response

