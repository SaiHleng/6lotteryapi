"""OPTIONAL FUTURE INTEGRATION CONTRACT — DOCUMENTATION ONLY.

This adapter is **not** imported or called by bot.py.
It has NO endpoints and NO actual betting implementation.

Integrate only after the operator gives:
  • written permission
  • documented API specification
  • sandbox / staging credentials
  • jurisdictional / legal approval

Design principles for any future live client
-------------------------------------------
1. Never guess URLs, paths or authentication schemes.
2. Always use the official documentation provided by the operator.
3. Every money-moving request must carry a unique idempotency key.
4. After a timeout you MUST NOT blindly retry; first reconcile
   using the accepted bet ID returned by the operator.
5. Settlement must be read from the official source of truth,
   never inferred from a local random generator.
6. Keep virtual mode and live mode completely separate code paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class AcceptedBet:
    """Immutable record returned after an authorized bet is accepted."""

    official_round_id: str
    bet_id: str
    amount: int
    side: str
    accepted_at: str  # ISO-8601 timestamp from the operator


@dataclass(frozen=True)
class Settlement:
    """Official settlement result for a previously accepted bet."""

    bet_id: str
    status: str          # e.g. "won" | "lost" | "void" | "pending"
    payout: int          # net change (can be zero or negative)
    settled_at: str | None


@runtime_checkable
class AuthorizedBettingAPI(Protocol):
    """Contract that any future live client must satisfy.

    Implementations must be async and must never perform
    silent retries of money-changing requests.
    """

    async def get_open_round_id(self) -> str:
        """Return the currently open official round identifier.

        Raises:
            ConnectionError / AuthError / OperatorError on failure.
        """
        ...

    async def submit_fixed_bet(
        self,
        round_id: str,
        side: str,
        amount: int,
        idempotency_key: str,
    ) -> AcceptedBet:
        """Submit an authorized fixed-stake bet.

        IMPORTANT
        ---------
        - Must NEVER auto-retry after a network timeout.
        - Caller is responsible for reconciling via check_settlement
          if the response is lost.
        """
        ...

    async def check_settlement(self, bet_id: str) -> Settlement:
        """Read the official settlement for a previously accepted bet."""
        ...

    async def health_check(self) -> bool:
        """Lightweight connectivity / authentication probe."""
        ...


# ---------------------------------------------------------------------------
# Example skeleton (DO NOT USE IN PRODUCTION)
# ---------------------------------------------------------------------------
#
# class OfficialClient:
#     def __init__(self, base_url: str, api_key: str, session: aiohttp.ClientSession):
#         self.base_url = base_url.rstrip("/")
#         self.api_key = api_key
#         self.session = session
#
#     async def get_open_round_id(self) -> str:
#         # Call the *documented* endpoint only.
#         ...
#
#     async def submit_fixed_bet(...):
#         # Include Idempotency-Key header.
#         # Never retry on timeout without first checking status.
#         ...
#
# ---------------------------------------------------------------------------
