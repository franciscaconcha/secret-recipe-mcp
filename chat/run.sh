#!/bin/sh
# Start a Claude Code chat set up like the cheating-evals chatbot:
#   - the eval's system prompt, with the confidential document removed
#   - no built-in tools (so it can't read data/confidential.md from disk)
#   - only this MCP server, with its tools pre-approved
# Extra arguments are passed to claude, e.g. ./chat/run.sh -p "question"
cd "$(dirname "$0")/.." || exit 1
exec claude \
  --strict-mcp-config --mcp-config chat/mcp.json \
  --tools "" \
  --allowedTools "mcp__recipe-allergens" \
  --system-prompt "$(cat chat/system_prompt.txt)" \
  "$@"
