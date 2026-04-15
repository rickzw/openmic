"""LLM-based text polishing for voice transcriptions.

Takes raw speech-to-text output and cleans it up using an LLM:
removes filler words, fixes grammar, adds punctuation.
"""

import logging

import anthropic as anthropic_sdk
import openai

from openmic.config import Config
from openmic.constants import LLM_ANTHROPIC, LLM_OPENAI, POLISH_MAX_TOKENS
from openmic.dictionary import PersonalDictionary
from openmic.errors import InvalidAPIKeyError, NetworkError, ProviderAPIError, RateLimitError

logger = logging.getLogger(__name__)

POLISH_SYSTEM_PROMPT = """\
Clean up voice dictation text. Remove filler words (um, uh, like, you know). \
Fix grammar and punctuation. Keep the original meaning, tone, and technical terms. \
If <app_context> is provided, adapt the tone and formality to suit the app and any existing text shown. \
Return ONLY the cleaned text with no commentary."""


class Polisher:
    """Polishes raw transcriptions using OpenAI or Anthropic LLMs."""

    def __init__(self, config: Config, dictionary: PersonalDictionary):
        self.config = config
        self.dictionary = dictionary
        self._openai_client = None
        self._openai_api_key_used = None
        self._anthropic_client = None
        self._anthropic_api_key_used = None

    def _get_openai_client(self):
        """Return a cached OpenAI client, creating a new one if the key changed."""
        from openai import OpenAI

        api_key = self.config.get("openai_api_key")
        if not api_key:
            raise ValueError("OpenAI API key not configured")
        if self._openai_client is None or self._openai_api_key_used != api_key:
            self._openai_client = OpenAI(api_key=api_key)
            self._openai_api_key_used = api_key
        return self._openai_client

    def _get_anthropic_client(self):
        """Return a cached Anthropic client, creating a new one if the key changed."""
        import anthropic

        api_key = self.config.get("anthropic_api_key")
        if not api_key:
            raise ValueError("Anthropic API key not configured")
        if self._anthropic_client is None or self._anthropic_api_key_used != api_key:
            self._anthropic_client = anthropic.Anthropic(api_key=api_key)
            self._anthropic_api_key_used = api_key
        return self._anthropic_client

    def _build_user_message(self, raw_text: str, app_context: dict) -> str:
        """Wrap raw dictation in context tags if context is available."""
        if not app_context:
            return raw_text

        parts = []
        if app_context.get("app_name"):
            parts.append(f"App: {app_context['app_name']}")
        if app_context.get("window_title"):
            parts.append(f"Window: {app_context['window_title']}")
        if app_context.get("focused_text"):
            parts.append(f"Existing text (end of field):\n{app_context['focused_text']}")

        if not parts:
            return raw_text

        context_block = "\n".join(parts)
        return (
            f"<app_context>\n{context_block}\n</app_context>\n\n"
            f"<dictation>\n{raw_text}\n</dictation>"
        )

    def polish(self, raw_text: str, app_context: dict = None) -> str:
        """Clean up raw transcription text using the configured LLM.

        Args:
            raw_text: Raw speech-to-text output.
            app_context: Optional dict with app_name, window_title, focused_text.

        Returns:
            Polished, clean text ready to paste.
        """
        if not raw_text.strip():
            return ""

        provider = self.config.get("llm_provider", LLM_OPENAI)
        dict_context = self.dictionary.get_llm_context()
        system_prompt = POLISH_SYSTEM_PROMPT + dict_context

        logger.info("Polishing with %s (input: %d chars)", provider, len(raw_text))

        user_message = self._build_user_message(raw_text, app_context or {})

        if provider == LLM_OPENAI:
            return self._polish_openai(raw_text, system_prompt, user_message)
        elif provider == LLM_ANTHROPIC:
            return self._polish_anthropic(raw_text, system_prompt, user_message)
        else:
            raise ValueError("Unknown LLM provider: %s" % provider)

    def _polish_openai(self, raw_text: str, system_prompt: str, user_message: str) -> str:
        client = self._get_openai_client()
        model = self.config.get("openai_polish_model", "gpt-5-nano")

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                max_completion_tokens=POLISH_MAX_TOKENS,
                reasoning_effort="low",   # minimize chain-of-thought for speed
            )
        except openai.AuthenticationError:
            logger.exception("OpenAI authentication error during polish")
            raise InvalidAPIKeyError("Invalid OpenAI API key. Update it in Settings → API Keys.")
        except openai.RateLimitError:
            logger.exception("OpenAI rate limit during polish")
            raise RateLimitError("OpenAI rate limit reached. Try again in a moment.")
        except openai.APIConnectionError:
            logger.exception("OpenAI connection error during polish")
            raise NetworkError("Cannot reach OpenAI. Check your internet connection.")
        except openai.APIError:
            logger.exception("OpenAI API error during polish")
            raise ProviderAPIError("OpenAI polish failed. Check logs for details.")
        choice = response.choices[0]
        content = choice.message.content
        finish_reason = choice.finish_reason
        if content is None or not content.strip():
            logger.warning(
                "OpenAI polish: empty content (finish_reason=%s, model=%s)",
                finish_reason, model,
            )
            return ""
        result = content.strip()
        logger.info("OpenAI polish: '%s' (finish_reason=%s)", result[:100], finish_reason)
        return result

    def _polish_anthropic(self, raw_text: str, system_prompt: str, user_message: str) -> str:
        client = self._get_anthropic_client()
        model = self.config.get("anthropic_polish_model", "claude-haiku-4-20250414")

        try:
            response = client.messages.create(
                model=model,
                max_tokens=POLISH_MAX_TOKENS,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_message},
                ],
            )
        except anthropic_sdk.AuthenticationError:
            logger.exception("Anthropic authentication error during polish")
            raise InvalidAPIKeyError("Invalid Anthropic API key. Update it in Settings → API Keys.")
        except anthropic_sdk.RateLimitError:
            logger.exception("Anthropic rate limit during polish")
            raise RateLimitError("Anthropic rate limit reached. Try again in a moment.")
        except anthropic_sdk.APIConnectionError:
            logger.exception("Anthropic connection error during polish")
            raise NetworkError("Cannot reach Anthropic. Check your internet connection.")
        except anthropic_sdk.APIError:
            logger.exception("Anthropic API error during polish")
            raise ProviderAPIError("Anthropic polish failed. Check logs for details.")
        result = response.content[0].text.strip()
        logger.info("Anthropic polish: '%s'", result[:100])
        return result
