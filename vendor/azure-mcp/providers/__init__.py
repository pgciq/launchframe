"""Cloud provider implementations for azure-mcp."""

from .azure import AzureProvider
from .base import (
    CloudProvider,
    CloudScope,
    ComputeActionResult,
    ResourceGroup,
    ResourceSummary,
)

__all__ = [
    "AzureProvider",
    "CloudProvider",
    "CloudScope",
    "ComputeActionResult",
    "ResourceGroup",
    "ResourceSummary",
]
