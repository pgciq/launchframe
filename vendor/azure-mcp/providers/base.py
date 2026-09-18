"""Provider-neutral interfaces and normalized cloud resource models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CloudScope:
    """A provider account, subscription, project, or equivalent scope."""

    scope_id: str
    display_name: str | None
    state: str | None
    scope_type: str


@dataclass(frozen=True)
class ResourceGroup:
    """A logical resource grouping when a provider exposes one."""

    name: str
    location: str | None
    tags: dict[str, Any] | None


@dataclass(frozen=True)
class ResourceSummary:
    """Common fields returned when listing cloud resources."""

    id: str | None
    name: str | None
    type: str | None
    location: str | None
    resource_group: str | None
    provisioning_state: str | None
    tags: dict[str, Any] | None


@dataclass(frozen=True)
class ComputeActionResult:
    """Normalized result for a provider compute power operation."""

    action: str
    resource_id: str
    completed: bool


class CloudProvider(ABC):
    """Provider-neutral operations used by the common cloud MCP tools.

    Authentication, scope resolution, SDK clients, resource identifiers, and
    provider-specific asynchronous operation handling belong to implementations.
    The MCP layer owns the stable tool contract and safety policy.
    """

    @abstractmethod
    def auth_status(self) -> list[CloudScope]:
        """List scopes accessible to the current identity."""

    @abstractmethod
    def list_resource_groups(self, scope_id: str | None = None) -> list[ResourceGroup]:
        """List logical resource groups for a scope, if supported."""

    @abstractmethod
    def list_resources(
        self,
        scope_id: str | None = None,
        resource_group: str | None = None,
    ) -> list[ResourceSummary]:
        """List resources, optionally within a logical resource group."""

    @abstractmethod
    def get_resource(
        self,
        resource_id: str,
        api_version: str,
        scope_id: str | None = None,
    ) -> Any:
        """Read a resource by its provider-specific identifier."""

    @abstractmethod
    def create_or_update_resource(
        self,
        resource_id: str,
        api_version: str,
        properties: dict[str, Any],
        scope_id: str | None = None,
    ) -> Any:
        """Create or update a resource."""

    @abstractmethod
    def delete_resource(
        self,
        resource_id: str,
        api_version: str,
        scope_id: str | None = None,
    ) -> None:
        """Delete a resource."""

    @abstractmethod
    def virtual_machine_action(
        self,
        resource_id: str,
        action: str,
        scope_id: str | None = None,
    ) -> ComputeActionResult:
        """Run a provider compute power operation."""
