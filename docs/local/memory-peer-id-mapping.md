# Memory Peer ID Mapping

Hermes 的 memory 子系统在写入前会对 gateway 传入的 `user_id` 做一次
provider 无关的规范化，把不同消息平台的 opaque ID 统一到一个 canonical
peer id 上。这个转换层在 `agent/peer_id_mapping.py`，测试在
`tests/agent/test_peer_id_mapping.py`。

## 文件

| 文件 | 作用 |
|---|---|
| `agent/peer_id_mapping.py` | 核心模块 — provider 无关的 peer id 转换层 |
| `tests/agent/test_peer_id_mapping.py` | 单元测试（23 个 case） |
| `run_agent.py:~1208` | 调用点 — 在 memory `initialize()` 前解析 peer id |

## 两步转换

### 1. 平台前缀

不同消息平台的 opaque ID 加上平台名前缀消歧：

| 平台 | 原始 ID | 转换后 |
|---|---|---|
| Slack | `U0ARWQL9JG1` | `slack-U0ARWQL9JG1` |
| Discord | `987654321` | `discord-987654321` |
| Telegram | `42` | `telegram-42` |

**例外**：CLI / local / cron / flush 等非消息来源**不加前缀**，保留已有
数据的 peer name（如 `honcho.json` 里的静态 `zwi`）。

### 2. 别名查找

通过 `config.yaml` 的 `memory.peer_id_aliases` 表，将多平台身份合并为
同一 peer：

```yaml
memory:
  peer_id_aliases:
    slack-U0ARWQL9JG1: zwi
    discord-987654321: zwi
    telegram-42: zwi
```

配置后，Slack / Discord / Telegram 的会话都写入同一个 `zwi` 记忆桶。

## 设计要点

- **分隔符用 `-` 而非 `:`** — Honcho session manager 会把非
  `[a-zA-Z0-9_-]` 字符重写为 `-`，用 `-` 保证配置和存储一致，且避免
  YAML 中需要额外引号。
- **幂等** — 已加前缀的 ID 再次调用不会重复加。
- **别名 key 必须用前缀形式** — `slack-U0ARWQL9JG1` 有效，裸
  `U0ARWQL9JG1` 无效。这是为了防止跨平台相同 opaque ID 造成歧义（同一个
  `abc` 在 Slack 和 Discord 上可能是不同的人）。
- **与具体 provider 无关** — 所有 memory provider（Honcho、mem0 等）
  都通过 `initialize()` 的 `user_id` 参数接收解析后的 peer id，无需改
  provider 代码。
