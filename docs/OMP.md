# Oh My Pi (OMP) integration

OMP can load a local stdio MCP server from `~/.omp/agent/mcp.json` or a
project's `.omp/mcp.json`. This repository provides a project-level `/pair`
command and skill in `.omp/`; they become available when OMP runs in this
checkout. For other projects, copy those two files to the corresponding
`~/.omp/agent/commands/` and `~/.omp/agent/skills/pair/` locations.

Add this server entry to `~/.omp/agent/mcp.json`, replacing the script path
with the absolute path of your checkout. Merge it with any existing servers:

```json
{
  "mcpServers": {
    "pair-bridge": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--locked", "--script", "/ABSOLUTE/PATH/pair-bridge/plugins/pair-bridge/scripts/server.py"],
      "timeout": 210000
    }
  }
}
```

Start OMP and run `/mcp test pair-bridge`. The tool list should include
`pair_devices`, `pair_list`, `pair_smart_ask`, `pair_compare`, and
`pair_diagnose`. Then try `/pair show installed models`. The same bridge
configuration file (`~/.pair-bridge.json`) is shared with Codex.

OMP may import some Codex MCP settings, but a plugin's `.mcp.json` is not a
portable OMP installation mechanism. Explicit OMP configuration above is the
supported path. Do not put API tokens in this file; export them in the OMP
process environment. See [OMP MCP configuration](https://github.com/can1357/oh-my-pi/blob/main/docs/mcp-config.md).
