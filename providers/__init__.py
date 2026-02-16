"""AI Budget Dashboard — Provider integrations."""

from providers.base import BaseProvider
from providers.anthropic_api import AnthropicProvider
from providers.openai_api import OpenAIProvider
from providers.google_api import GoogleProvider
from providers.xai_api import XAIProvider

PROVIDERS = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "google": GoogleProvider,
    "xai": XAIProvider,
}

__all__ = [
    "BaseProvider",
    "AnthropicProvider",
    "OpenAIProvider",
    "GoogleProvider",
    "XAIProvider",
    "PROVIDERS",
]
