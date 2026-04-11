"""Peer-id mapping for memory contexts.

Generic, provider-agnostic translation layer that runs **only** on the path
into the memory subsystem. Two transforms, applied in order:

1. **Platform prefix.** The same human appears under different opaque IDs on
   different messaging platforms (Slack ``U0ARWQL9JG1``, Discord ``987654321``,
   Telegram ``42``). Raw IDs collide in semantics and can clash across
   platforms. Namespacing them with the platform name disambiguates the
   underlying peer id in any backend (Honcho, mem0, ...).

2. **Alias lookup.** A user-supplied table maps the prefixed id to a canonical
   peer id, so multiple platform identities for the same person collapse into
   one memory bucket. Example::

       memory:
         peer_id_aliases:
           slack-U0ARWQL9JG1: zwi
           discord-987654321: zwi

   Both Slack and Discord turns then write to the same ``zwi`` peer.

CLI / local sessions are NOT prefixed — they already use a static peer name
(e.g. ``zwi`` from ``honcho.json``) and prefixing would orphan existing data.

Why this layer is independent of any specific provider: every memory provider
in this repo (Honcho, mem0, ...) accepts ``user_id`` via ``initialize()``
kwargs and uses it as its scoping key. Resolving the id once before that call
gives every provider the canonical form for free, with zero changes to
provider code.

Format note: the prefix separator is ``-``. The "obvious" choice would be
``:`` (matching URN/DID/atproto namespace conventions), but Honcho's session
manager sanitizes peer ids against ``[a-zA-Z0-9_-]`` and rewrites every other
character to ``-`` — so ``slack:U0ARWQL9JG1`` would silently become
``slack-U0ARWQL9JG1`` in the backend, leaving config and storage out of sync.
Picking ``-`` here makes "what you configure" and "what's stored" identical,
and avoids needing YAML quoting for alias keys.
"""

from __future__ import annotations

import logging
from typing import Mapping, Optional

logger = logging.getLogger(__name__)

# Platforms that should NOT receive a prefix. These are non-messaging origins
# where the existing peer-id semantics (static config or session-derived names)
# must be preserved.
_NON_MESSAGING_PLATFORMS = frozenset({"cli", "local", "cron", "flush", ""})

_PREFIX_SEP = "-"


def apply_platform_prefix(user_id: str, platform: Optional[str]) -> str:
    """Return ``user_id`` namespaced by ``platform``.

    >>> apply_platform_prefix("U0ARWQL9JG1", "slack")
    'slack-U0ARWQL9JG1'
    >>> apply_platform_prefix("zwi", "cli")
    'zwi'
    >>> apply_platform_prefix("zwi", None)
    'zwi'

    Idempotent: calling on an already-prefixed id with the same platform is a
    no-op, so callers can re-resolve safely.
    """
    if not user_id:
        return user_id
    plat = (platform or "").strip().lower()
    if plat in _NON_MESSAGING_PLATFORMS:
        return user_id
    expected_prefix = f"{plat}{_PREFIX_SEP}"
    if user_id.startswith(expected_prefix):
        return user_id
    return f"{expected_prefix}{user_id}"


def resolve_memory_peer_id(
    user_id: Optional[str],
    platform: Optional[str],
    aliases: Optional[Mapping[str, str]] = None,
) -> Optional[str]:
    """Resolve a gateway user_id to its canonical memory peer id.

    Two-step resolution:
        1. Apply the platform prefix (no-op for CLI / non-messaging platforms).
        2. Look up the prefixed id in ``aliases``. If matched, return the alias.
           Otherwise return the prefixed id.

    Returns ``None`` when ``user_id`` is falsy, so callers can preserve the
    "no override — use the provider's static config" branch.

    Alias keys must be in **prefixed form** (``slack-U0ARWQL9JG1``). Raw-form
    keys are not honored — keeping the table strict avoids ambiguity when the
    same opaque id could mean different people on different platforms.
    """
    if not user_id:
        return None
    prefixed = apply_platform_prefix(user_id, platform)
    if aliases:
        mapped = aliases.get(prefixed)
        if mapped:
            if mapped != user_id:
                logger.info(
                    "Memory peer id resolved: %s (%s) -> %s (via alias %s)",
                    user_id, platform or "", mapped, prefixed,
                )
            return mapped
    if prefixed != user_id:
        logger.info(
            "Memory peer id resolved: %s (%s) -> %s",
            user_id, platform or "", prefixed,
        )
    return prefixed
