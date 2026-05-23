# BotSpace MCP Server

Manage your Telegram bots on [BotSpace](https://botspace.uz) from any AI agent
(Claude Desktop, Cursor, Windsurf, Claude Code, etc.) using the
[Model Context Protocol](https://modelcontextprotocol.io/).

## Connection

The MCP server runs as a global HTTP service at:

```
https://botspace.uz/mcp/sse
```

Authentication: pass your BotSpace access token as a Bearer header.

## Claude Desktop setup

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "botspace": {
      "url": "https://botspace.uz/mcp/sse",
      "headers": {
        "Authorization": "Bearer YOUR_BOTSPACE_TOKEN"
      }
    }
  }
}
```

## Claude Code setup

```bash
claude mcp add botspace --transport sse https://botspace.uz/mcp/sse
```

## Cursor / Windsurf setup

In `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "botspace": {
      "url": "https://botspace.uz/mcp/sse",
      "headers": {
        "Authorization": "Bearer YOUR_BOTSPACE_TOKEN"
      }
    }
  }
}
```

## Available tools

| Tool | Description |
|------|-------------|
| `botspace_list_projects` | List all your bot projects |
| `botspace_create_project` | Create a new bot project |
| `botspace_get_flow` | Load a bot's flow (nodes + edges) |
| `botspace_upsert_node` | Add or update a node in the flow |
| `botspace_remove_node` | Remove a node and its edges |
| `botspace_connect_nodes` | Connect two nodes with an edge |
| `botspace_disconnect_nodes` | Remove an edge by ID |
| `botspace_validate_flow` | Check flow for errors |
| `botspace_save_flow` | Persist flow to backend |
| `botspace_deploy` | Deploy bot to production |
| `botspace_list_node_types` | List all node types with required fields |
| `botspace_set_env` | Set an environment variable |
| `botspace_get_subscription` | Get plan & token usage |

## Example

Ask your AI agent:

> Create a Telegram bot called "Hello Bot" with a /start trigger that replies "Salom!". Save and deploy it.

## Self-hosting

```bash
pip install botspace-mcp
MCP_PORT=8200 BOTSPACE_API_URL=https://api.botspace.uz botspace-mcp
```

Or via Docker:

```bash
docker build -t botspace-mcp .
docker run -p 8200:8200 botspace-mcp
```
