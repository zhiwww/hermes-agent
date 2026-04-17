# Mem0 Memory Provider

Server-side LLM fact extraction with semantic search, reranking, and automatic deduplication.

## Requirements

- `pip install mem0ai`
- Mem0 API key — from [app.mem0.ai](https://app.mem0.ai) (Platform) or your self-hosted instance

## Setup

```bash
hermes memory setup    # select "mem0"
```

Or manually:
```bash
hermes config set memory.provider mem0
echo "MEM0_API_KEY=your-key" >> ~/.hermes/.env
# For self-hosted instances, also set:
# echo "MEM0_HOST=http://localhost:8080" >> ~/.hermes/.env
```

## Config

Config file: `$HERMES_HOME/mem0.json`

| Key | Default | Description |
|-----|---------|-------------|
| `host` | *(empty — uses `https://api.mem0.ai`)* | API base URL; set for self-hosted instances |
| `user_id` | `hermes-user` | User identifier on Mem0 |
| `agent_id` | `hermes` | Agent identifier |
| `rerank` | `true` | Enable reranking for recall |

## Tools

| Tool | Description |
|------|-------------|
| `mem0_profile` | All stored memories about the user |
| `mem0_search` | Semantic search with optional reranking |
| `mem0_conclude` | Store a fact verbatim (no LLM extraction) |
