# azure-mcp

`azure-mcp` is a client-neutral MCP server for Microsoft Azure Resource Manager. It uses Azure management SDK clients and `DefaultAzureCredential` to inspect and, when explicitly enabled, modify Azure resources. It communicates with any compatible MCP host over stdio and does not depend on Pi.

## Installation

### Prerequisites

- Python 3.10 or newer
- An Azure identity with the required RBAC permissions
- Azure CLI for the recommended local development login, or service-principal credentials
- Network access to Azure management endpoints

Azure CLI is only required when using `az login`. Install it from Microsoft's cross-platform instructions: <https://learn.microsoft.com/cli/azure/install-azure-cli>. Service-principal, managed-identity, and other supported credential sources can be used without Azure CLI.

### Linux/macOS

```bash
cd azure-mcp
python3 -m venv .venv
./.venv/bin/python -m pip install -e .
./.venv/bin/azure-mcp
```

### Windows PowerShell

```powershell
cd azure-mcp
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\azure-mcp.exe
```

## Authentication and Configuration

For local development, the `az` commands work in PowerShell and Linux/macOS shells; only the environment-variable syntax differs:

```text
az login
az account set --subscription "<subscription-id>"
```

```powershell
# Windows PowerShell
$env:AZURE_SUBSCRIPTION_ID = "<subscription-id>"
```

```bash
# Linux/macOS
export AZURE_SUBSCRIPTION_ID="<subscription-id>"
```

Service-principal authentication is also supported:

```powershell
# Windows PowerShell
$env:AZURE_TENANT_ID = "<tenant-id>"
$env:AZURE_CLIENT_ID = "<client-id>"
$env:AZURE_CLIENT_SECRET = "<client-secret>"
$env:AZURE_SUBSCRIPTION_ID = "<subscription-id>"
```

```bash
# Linux/macOS
export AZURE_TENANT_ID="<tenant-id>"
export AZURE_CLIENT_ID="<client-id>"
export AZURE_CLIENT_SECRET="<client-secret>"
export AZURE_SUBSCRIPTION_ID="<subscription-id>"
```

`subscription_id` may be supplied to individual tools. For resource-ID operations, the subscription can also be inferred from a complete Azure resource ID.

## Dependencies

- `mcp>=1.2.0,<2.0.0` — MCP protocol and `FastMCP` server implementation
- `azure-identity>=1.19.0` — Azure credential chain
- `azure-mgmt-resource>=23.2.0` — resource groups and generic resource operations
- `azure-mgmt-compute>=34.0.0` — virtual machine operations
- `azure-mgmt-sql>=3.0.1` — Azure SQL firewall rules
- `azure-mgmt-subscription>=3.1.1` — subscription discovery

## Safety Controls

Read operations are enabled by default. Resource creation, updates, VM power actions, and SQL firewall changes require:

```powershell
# Windows PowerShell
$env:AZURE_MCP_ALLOW_MUTATIONS = "true"
```

```bash
# Linux/macOS
export AZURE_MCP_ALLOW_MUTATIONS="true"
```

Resource deletion additionally requires:

```powershell
# Windows PowerShell
$env:AZURE_MCP_ALLOW_DELETE = "true"
```

```bash
# Linux/macOS
export AZURE_MCP_ALLOW_DELETE="true"
```

The Azure identity must also have the corresponding RBAC permissions. Use the least-privilege role assignments possible, and avoid enabling mutation flags in production unless operationally required.

## Azure RBAC Permissions

The environment-variable safety switches do not grant Azure permissions. Assign the least-privilege role required by the operation:

- `Reader` or an equivalent custom role for listing and reading resources
- `Contributor` or a resource-specific custom role for create/update operations
- `Virtual Machine Contributor` or an equivalent role for VM power operations
- `SQL Server Contributor` or an equivalent role for SQL firewall rules
- The corresponding delete permission for resource deletion

## Direct MCP registration and optional Pi integration

Any MCP-compatible host can register the `azure-mcp` executable directly using the stdio configuration described in the root README. An optional consumer-project Pi bridge can start this server from the Toolkit's virtual environment according to `.pi/mcp.json`. When used, configure Azure credentials in the project's local configuration or startup environment; `AZURE_SUBSCRIPTION_ID` is required by the example profile.

Verify the setup by calling `azure_auth_status`. It should return the subscriptions accessible to the current identity. If it fails, check `az login`, `AZURE_SUBSCRIPTION_ID`, and Azure RBAC permissions.

## MCP Tools

- `azure_auth_status` — lists subscriptions accessible to the current identity
- `list_resource_groups` — lists resource groups in a subscription
- `list_resources` — lists resources across a subscription or resource group
- `get_resource` — reads a resource by full resource ID and API version
- `create_or_update_resource` — creates or updates a resource; mutation flag required
- `virtual_machine_action` — starts, stops, restarts, or deallocates a VM; mutation flag required
- `add_sql_firewall_rule` — creates or updates an Azure SQL firewall rule; mutation flag required
- `delete_resource` — deletes a resource by ID and API version; both safety flags required

Resource operations requiring an API version expect the version supported by the target resource provider, such as `2023-09-01`. VM operations wait for the asynchronous Azure operation to complete before returning.

## Technical Architecture

```text
MCP Client --stdio--> FastMCP tool layer
                              |
                 validation / safety policy
                              |
                    CloudProvider interface
                              |
                      AzureProvider
                              |
        +---------------------+---------------------+
        |                     |                     |
 ResourceManagement   ComputeManagement       SqlManagement
 Subscription clients       Client               Client
        |                     |                     |
 Azure Resource Manager  Azure VM control     Azure SQL firewall
```

The MCP tool layer owns the stable tool contract, input validation, mutation/delete safety gates, and JSON response shapes. `providers/base.py` defines provider-neutral scope, resource, and compute-operation models; `providers/azure.py` contains Azure credential handling, subscription resolution, Azure resource ID parsing, SDK clients, and asynchronous operation handling.

The current Server targets Azure, but the provider boundary is intentionally designed for future AWS, GCP, Alibaba Cloud, or other provider implementations. Provider-specific operations such as Azure SQL firewall rules remain in the Azure provider rather than being forced into an artificial cross-cloud abstraction.
