"""Unit tests for the peer-id mapping layer used on the path into memory.

Covers:
- platform prefix application (and the CLI/local exemption)
- alias-table lookup (canonicalizing the same human across channels)
- idempotency and edge cases (None / empty user_id)
"""

from agent.peer_id_mapping import apply_platform_prefix, resolve_memory_peer_id


# ---------------------------------------------------------------------------
# apply_platform_prefix
# ---------------------------------------------------------------------------


class TestApplyPlatformPrefix:
    def test_slack_id_gets_prefixed(self):
        assert apply_platform_prefix("U0ARWQL9JG1", "slack") == "slack-U0ARWQL9JG1"

    def test_discord_id_gets_prefixed(self):
        assert apply_platform_prefix("987654321", "discord") == "discord-987654321"

    def test_telegram_id_gets_prefixed(self):
        assert apply_platform_prefix("42", "telegram") == "telegram-42"

    def test_cli_is_not_prefixed(self):
        # CLI uses static peer names from honcho.json — must not be prefixed
        # or existing memory data orphans.
        assert apply_platform_prefix("zwi", "cli") == "zwi"

    def test_local_is_not_prefixed(self):
        assert apply_platform_prefix("zwi", "local") == "zwi"

    def test_none_platform_is_not_prefixed(self):
        assert apply_platform_prefix("zwi", None) == "zwi"

    def test_empty_platform_is_not_prefixed(self):
        assert apply_platform_prefix("zwi", "") == "zwi"

    def test_cron_context_is_not_prefixed(self):
        assert apply_platform_prefix("zwi", "cron") == "zwi"

    def test_flush_context_is_not_prefixed(self):
        assert apply_platform_prefix("zwi", "flush") == "zwi"

    def test_platform_name_is_lowercased(self):
        assert apply_platform_prefix("U123", "Slack") == "slack-U123"
        assert apply_platform_prefix("U123", "DISCORD") == "discord-U123"

    def test_platform_name_is_stripped(self):
        assert apply_platform_prefix("U123", "  slack  ") == "slack-U123"

    def test_idempotent_on_already_prefixed(self):
        once = apply_platform_prefix("U123", "slack")
        twice = apply_platform_prefix(once, "slack")
        assert once == "slack-U123"
        assert twice == "slack-U123"

    def test_empty_user_id_returned_unchanged(self):
        assert apply_platform_prefix("", "slack") == ""


# ---------------------------------------------------------------------------
# resolve_memory_peer_id
# ---------------------------------------------------------------------------


class TestResolveMemoryPeerId:
    def test_none_user_id_returns_none(self):
        assert resolve_memory_peer_id(None, "slack", {}) is None

    def test_empty_user_id_returns_none(self):
        assert resolve_memory_peer_id("", "slack", {}) is None

    def test_no_alias_table_returns_prefixed(self):
        assert resolve_memory_peer_id("U0ARWQL9JG1", "slack", None) == "slack-U0ARWQL9JG1"

    def test_empty_alias_table_returns_prefixed(self):
        assert resolve_memory_peer_id("U0ARWQL9JG1", "slack", {}) == "slack-U0ARWQL9JG1"

    def test_cli_with_no_aliases_returns_raw(self):
        # CLI exemption flows through resolve too.
        assert resolve_memory_peer_id("zwi", "cli", None) == "zwi"

    def test_alias_match_returns_canonical(self):
        aliases = {"slack-U0ARWQL9JG1": "zwi"}
        assert resolve_memory_peer_id("U0ARWQL9JG1", "slack", aliases) == "zwi"

    def test_multiple_platforms_alias_to_same_canonical(self):
        # The whole point: collapse multi-platform identities into one peer.
        aliases = {
            "slack-U0ARWQL9JG1": "zwi",
            "discord-987654321": "zwi",
            "telegram-42": "zwi",
        }
        assert resolve_memory_peer_id("U0ARWQL9JG1", "slack", aliases) == "zwi"
        assert resolve_memory_peer_id("987654321", "discord", aliases) == "zwi"
        assert resolve_memory_peer_id("42", "telegram", aliases) == "zwi"

    def test_alias_miss_falls_through_to_prefixed(self):
        aliases = {"slack-UAAAA": "zwi"}
        assert resolve_memory_peer_id("UBBBB", "slack", aliases) == "slack-UBBBB"

    def test_raw_form_alias_key_is_not_honored(self):
        # Strict format: alias keys MUST be in prefixed form.
        aliases = {"U0ARWQL9JG1": "zwi"}
        assert (
            resolve_memory_peer_id("U0ARWQL9JG1", "slack", aliases)
            == "slack-U0ARWQL9JG1"
        )

    def test_cli_id_can_still_be_aliased(self):
        # CLI ids aren't prefixed, so the alias key for them is the raw id.
        aliases = {"zwi": "wei.zhi"}
        assert resolve_memory_peer_id("zwi", "cli", aliases) == "wei.zhi"

    def test_alias_value_with_no_collision_with_other_platform(self):
        # Same opaque id under two platforms should NOT collide.
        aliases = {"slack-abc": "alice", "discord-abc": "bob"}
        assert resolve_memory_peer_id("abc", "slack", aliases) == "alice"
        assert resolve_memory_peer_id("abc", "discord", aliases) == "bob"
