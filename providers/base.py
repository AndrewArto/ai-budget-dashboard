"""Base provider class for AI API usage tracking."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class UsageData:
    """Holds usage data for a single provider."""

    provider_id: str
    provider_name: str
    current_spend: float = 0.0
    monthly_budget: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    last_updated: datetime = field(default_factory=datetime.now)

    @property
    def remaining(self) -> float:
        return max(0.0, self.monthly_budget - self.current_spend)

    @property
    def usage_percent(self) -> float:
        if self.monthly_budget <= 0:
            return 0.0
        return min(100.0, (self.current_spend / self.monthly_budget) * 100.0)

    def format_spend(self) -> str:
        return f"${self.current_spend:.2f}/${self.monthly_budget:.0f}"

    def format_tokens(self) -> str:
        return f"{_format_count(self.tokens_in)} in / {_format_count(self.tokens_out)} out"


def _format_count(n: int) -> str:
    """Format token count: 1234567 -> '1.2M', 123456 -> '123K'."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    elif n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


class BaseProvider(ABC):
    """Abstract base class for AI provider integrations."""

    provider_id: str
    provider_name: str

    @abstractmethod
    def fetch_usage(self, api_key: str | None, budget: float) -> UsageData:
        """Fetch current month's usage data.

        Args:
            api_key: API key for the provider (may be None for local tracking).
            budget: Monthly budget in USD.

        Returns:
            UsageData with current spend and token counts.
        """
        ...
