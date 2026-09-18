"""Azure cloud provider implementation."""

from __future__ import annotations

import os
import re
from typing import Any

from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.resource.resources import ResourceManagementClient
from azure.mgmt.sql import SqlManagementClient
from azure.mgmt.sql.models import FirewallRule
from azure.mgmt.subscription import SubscriptionClient

from .base import (
    CloudProvider,
    CloudScope,
    ComputeActionResult,
    ResourceGroup,
    ResourceSummary,
)


class AzureProvider(CloudProvider):
    """Microsoft Azure Resource Manager provider."""

    def __init__(self) -> None:
        self._credential: DefaultAzureCredential | None = None

    def credential(self) -> DefaultAzureCredential:
        if self._credential is None:
            # This server is normally used from a developer workstation where
            # Azure CLI is the active credential. Probing the managed identity
            # endpoint first can stall every ARM request when no IMDS endpoint
            # exists (or when a corporate proxy intercepts that address).
            self._credential = DefaultAzureCredential(
                exclude_interactive_browser_credential=False,
                exclude_managed_identity_credential=True,
            )
        return self._credential

    @staticmethod
    def subscription_id(subscription_id: str | None = None, resource_id: str | None = None) -> str:
        """Resolve a subscription from the argument, environment, or resource ID."""
        value = (subscription_id or os.getenv("AZURE_SUBSCRIPTION_ID") or "").strip()
        if not value and resource_id:
            match = re.match(r"^/subscriptions/([^/]+)(?:/|$)", resource_id, re.IGNORECASE)
            if match:
                value = match.group(1)
        if not value:
            raise ValueError(
                "subscription_id is required; set AZURE_SUBSCRIPTION_ID or provide it explicitly"
            )
        return value

    def resource_client(
        self,
        subscription_id: str | None = None,
        resource_id: str | None = None,
    ) -> ResourceManagementClient:
        return ResourceManagementClient(
            self.credential(), self.subscription_id(subscription_id, resource_id)
        )

    def compute_client(
        self,
        subscription_id: str | None = None,
        resource_id: str | None = None,
    ) -> ComputeManagementClient:
        return ComputeManagementClient(
            self.credential(), self.subscription_id(subscription_id, resource_id)
        )

    def sql_client(
        self,
        subscription_id: str | None = None,
        resource_id: str | None = None,
    ) -> SqlManagementClient:
        return SqlManagementClient(self.credential(), self.subscription_id(subscription_id, resource_id))

    @staticmethod
    def virtual_machine_parts(resource_id: str) -> tuple[str, str, str]:
        """Return subscription, resource group, and VM name from an Azure resource ID."""
        match = re.match(
            r"^/subscriptions/([^/]+)/resourceGroups/([^/]+)/providers/"
            r"Microsoft\.Compute/virtualMachines/([^/]+)$",
            resource_id,
            re.IGNORECASE,
        )
        if not match:
            raise ValueError(
                "resource_id must be a full Microsoft.Compute/virtualMachines resource ID "
                "without a child resource"
            )
        return match.group(1), match.group(2), match.group(3)

    def auth_status(self) -> list[CloudScope]:
        subscriptions = SubscriptionClient(self.credential()).subscriptions.list()
        return [
            CloudScope(
                scope_id=item.subscription_id,
                display_name=item.display_name,
                state=item.state,
                scope_type="subscription",
            )
            for item in subscriptions
        ]

    def list_resource_groups(self, scope_id: str | None = None) -> list[ResourceGroup]:
        client = self.resource_client(scope_id)
        return [
            ResourceGroup(name=group.name, location=group.location, tags=group.tags)
            for group in client.resource_groups.list()
        ]

    def list_resources(
        self,
        scope_id: str | None = None,
        resource_group: str | None = None,
    ) -> list[ResourceSummary]:
        client = self.resource_client(scope_id)
        resources = (
            client.resources.list_by_resource_group(resource_group)
            if resource_group
            else client.resources.list()
        )
        summaries: list[ResourceSummary] = []
        for item in resources:
            resource_group_name = None
            if item.id and "/resourceGroups/" in item.id:
                resource_group_name = item.id.split("/resourceGroups/")[1].split("/")[0]
            summaries.append(
                ResourceSummary(
                    id=item.id,
                    name=item.name,
                    type=item.type,
                    location=item.location,
                    resource_group=resource_group_name,
                    provisioning_state=getattr(item, "provisioning_state", None),
                    tags=item.tags,
                )
            )
        return summaries

    def get_resource(
        self,
        resource_id: str,
        api_version: str,
        scope_id: str | None = None,
    ) -> Any:
        return self.resource_client(scope_id, resource_id).resources.get_by_id(
            resource_id, api_version
        )

    def create_or_update_resource(
        self,
        resource_id: str,
        api_version: str,
        properties: dict[str, Any],
        scope_id: str | None = None,
    ) -> Any:
        poller = self.resource_client(scope_id, resource_id).resources.begin_create_or_update_by_id(
            resource_id, api_version, properties
        )
        return poller.result()

    def add_sql_firewall_rule(
        self,
        resource_group: str,
        server_name: str,
        rule_name: str,
        start_ip_address: str,
        end_ip_address: str | None = None,
        subscription_id: str | None = None,
    ) -> dict[str, Any]:
        end_ip = (end_ip_address or start_ip_address).strip()
        rule = self.sql_client(subscription_id).firewall_rules.create_or_update(
            resource_group,
            server_name,
            rule_name,
            FirewallRule(
                start_ip_address=start_ip_address,
                end_ip_address=end_ip,
            ),
        )
        return {
            "created": True,
            "resource_group": resource_group,
            "server_name": server_name,
            "rule_name": rule_name,
            "start_ip_address": getattr(rule, "start_ip_address", start_ip_address),
            "end_ip_address": getattr(rule, "end_ip_address", end_ip),
        }

    def virtual_machine_action(
        self,
        resource_id: str,
        action: str,
        scope_id: str | None = None,
    ) -> ComputeActionResult:
        subscription_id, resource_group, vm_name = self.virtual_machine_parts(resource_id)
        selected_subscription = scope_id or subscription_id
        operations = {
            "start": "begin_start",
            "stop": "begin_power_off",
            "restart": "begin_restart",
            "deallocate": "begin_deallocate",
        }
        normalized_action = action.strip().lower()
        operation_name = operations.get(normalized_action)
        if operation_name is None:
            raise ValueError("action must be one of: start, stop, restart, deallocate")

        operation = getattr(
            self.compute_client(selected_subscription, resource_id).virtual_machines,
            operation_name,
        )
        operation(resource_group, vm_name).result()
        return ComputeActionResult(
            action=normalized_action,
            resource_id=resource_id,
            completed=True,
        )

    def delete_resource(
        self,
        resource_id: str,
        api_version: str,
        scope_id: str | None = None,
    ) -> None:
        poller = self.resource_client(scope_id, resource_id).resources.begin_delete_by_id(
            resource_id, api_version
        )
        poller.result()
