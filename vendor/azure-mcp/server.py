"""MCP server for cloud resource operations.

The current provider is Microsoft Azure. The MCP tool layer owns the stable
contract and safety policy while provider-specific SDK and resource semantics
live under ``providers/``.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

try:
    from providers.azure import AzureProvider
    from providers.base import CloudProvider
except ModuleNotFoundError as error:
    # Keep direct loading via importlib (used by repository tests) working even
    # though the installed console script normally has azure-mcp on sys.path.
    if error.name not in {"providers", "providers.azure", "providers.base"}:
        raise
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from providers.azure import AzureProvider
    from providers.base import CloudProvider

mcp = FastMCP("azure-mcp")
_provider: CloudProvider = AzureProvider()


def _azure_provider() -> AzureProvider:
    """Return the configured provider as an Azure provider."""
    if not isinstance(_provider, AzureProvider):
        raise TypeError("The configured provider is not Azure")
    return _provider


def _credential_for_azure() -> Any:
    return _azure_provider().credential()


def _subscription_id(subscription_id: str | None = None, resource_id: str | None = None) -> str:
    return _azure_provider().subscription_id(subscription_id, resource_id)


def _resource_client(subscription_id: str | None = None, resource_id: str | None = None) -> Any:
    return _azure_provider().resource_client(subscription_id, resource_id)


def _compute_client(subscription_id: str | None = None, resource_id: str | None = None) -> Any:
    return _azure_provider().compute_client(subscription_id, resource_id)


def _sql_client(subscription_id: str | None = None, resource_id: str | None = None) -> Any:
    return _azure_provider().sql_client(subscription_id, resource_id)


def _virtual_machine_parts(resource_id: str) -> tuple[str, str, str]:
    return AzureProvider.virtual_machine_parts(resource_id)


def _json(value: Any) -> str:
    if hasattr(value, "as_dict"):
        value = value.as_dict()
    return json.dumps(value, default=str, indent=2)


def _mutations_enabled() -> None:
    if os.getenv("AZURE_MCP_ALLOW_MUTATIONS", "").lower() not in {"1", "true", "yes"}:
        raise PermissionError(
            "Mutating operations are disabled. Set AZURE_MCP_ALLOW_MUTATIONS=true "
            "before starting azure-mcp."
        )


def _deletes_enabled() -> None:
    _mutations_enabled()
    if os.getenv("AZURE_MCP_ALLOW_DELETE", "").lower() not in {"1", "true", "yes"}:
        raise PermissionError(
            "Delete operations are disabled. Set AZURE_MCP_ALLOW_DELETE=true "
            "before starting azure-mcp."
        )


@mcp.tool()
def azure_auth_status() -> str:
    """Verify Azure credentials by listing accessible subscriptions."""
    return _json([
        {
            "subscription_id": scope.scope_id,
            "display_name": scope.display_name,
            "state": scope.state,
        }
        for scope in _provider.auth_status()
    ])


@mcp.tool()
def list_resource_groups(subscription_id: str | None = None) -> str:
    """List resource groups in an Azure subscription."""
    return _json([asdict(group) for group in _provider.list_resource_groups(subscription_id)])


@mcp.tool()
def list_resources(subscription_id: str | None = None, resource_group: str | None = None) -> str:
    """List Azure resources, optionally limited to one resource group."""
    return _json([
        asdict(resource)
        for resource in _provider.list_resources(subscription_id, resource_group)
    ])


@mcp.tool()
def get_resource(resource_id: str, api_version: str, subscription_id: str | None = None) -> str:
    """Get a resource by full Azure resource ID and API version."""
    if not resource_id.startswith("/subscriptions/"):
        raise ValueError("resource_id must be a full Azure resource ID")
    return _json(_provider.get_resource(resource_id, api_version, subscription_id))


@mcp.tool()
def create_or_update_resource(
    resource_id: str,
    api_version: str,
    properties: dict[str, Any],
    subscription_id: str | None = None,
) -> str:
    """Create or update a resource by ID. Disabled unless mutations are enabled."""
    _mutations_enabled()
    if not resource_id.startswith("/subscriptions/"):
        raise ValueError("resource_id must be a full Azure resource ID")
    return _json(
        _provider.create_or_update_resource(
            resource_id, api_version, properties, subscription_id
        )
    )


@mcp.tool()
def add_sql_firewall_rule(
    resource_group: str,
    server_name: str,
    rule_name: str,
    start_ip_address: str,
    end_ip_address: str | None = None,
    subscription_id: str | None = None,
) -> str:
    """Add or update an Azure SQL Server firewall rule.

    Mutations are disabled unless AZURE_MCP_ALLOW_MUTATIONS is enabled. If
    end_ip_address is omitted, the rule covers only start_ip_address.
    """
    _mutations_enabled()
    if not resource_group.strip() or not server_name.strip() or not rule_name.strip():
        raise ValueError("resource_group, server_name, and rule_name are required")
    if not start_ip_address.strip():
        raise ValueError("start_ip_address is required")
    return _json(_azure_provider().add_sql_firewall_rule(
        resource_group.strip(),
        server_name.strip(),
        rule_name.strip(),
        start_ip_address.strip(),
        end_ip_address,
        subscription_id,
    ))


@mcp.tool()
def virtual_machine_action(
    resource_id: str,
    action: str,
    subscription_id: str | None = None,
) -> str:
    """Run a supported power operation on an Azure virtual machine.

    Supported actions are ``start``, ``stop``, ``restart``, and ``deallocate``.
    Mutating operations are disabled unless AZURE_MCP_ALLOW_MUTATIONS is enabled.
    """
    _mutations_enabled()
    return _json(asdict(_provider.virtual_machine_action(resource_id, action, subscription_id)))


@mcp.tool()
def delete_resource(resource_id: str, api_version: str, subscription_id: str | None = None) -> str:
    """Delete a resource by ID. Requires both mutation and delete flags."""
    _deletes_enabled()
    if not resource_id.startswith("/subscriptions/"):
        raise ValueError("resource_id must be a full Azure resource ID")
    _provider.delete_resource(resource_id, api_version, subscription_id)
    return _json({"deleted": True, "resource_id": resource_id})


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
