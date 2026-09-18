# Architecture and security

- The product uses a client-neutral MCP integration layer.
- Read-only operations are enabled by default.
- Mutating operations require explicit approval gates.
- Credentials remain outside product source files.
