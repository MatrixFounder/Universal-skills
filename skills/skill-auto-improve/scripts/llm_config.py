#!/usr/bin/env python3
"""Vendor-agnostic LLM completion layer for skill-auto-improve.

Ported from pre-project-artifacts-bootstrap/skills/common/llm_config.py
(house-style multi-provider wrapper on native SDKs — NOT litellm) with two
additions required by this skill:

  1. usage extraction for anthropic (input/output tokens) and gemini
     (usage_metadata) — the upstream returned {} for those, but we need
     token counts for the --max-tokens budget.
  2. OPENAI_BASE_URL passthrough into openai.OpenAI(base_url=...) so the
     same code drives OpenAI-compatible gateways (Hermes Gateway, Ollama,
     vLLM, Together, Groq).

Provider is selected by DEFAULT_PROVIDER (gemini|anthropic|openai). Per-task
parameters come from config/llm_profiles.yaml. Secrets come from .env /
environment. Each provider SDK is imported lazily so the skill installs even
when only one provider's SDK is present.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import yaml

try:
    from dotenv import load_dotenv
except ImportError:  # dotenv is convenience-only; env vars still work without it
    def load_dotenv(*_args, **_kwargs):  # type: ignore
        return False

try:
    from google import genai
except ImportError:
    genai = None

try:
    import anthropic
except ImportError:
    anthropic = None

try:
    import openai
except ImportError:
    openai = None


def find_skill_root() -> Path:
    """Skill root = parent of the scripts/ directory holding this file."""
    return Path(__file__).resolve().parent.parent


class LLMRetryableError(RuntimeError):
    """Exception type for retriable LLM failures (timeout/429/connection)."""


class LLMConfigManager:
    """Configuration manager + unified call surface for LLM scripts.

    Loads secrets from .env and parameters from config/llm_profiles.yaml.
    Supports an optional fallback model chain per provider.
    """

    def __init__(self, profile_name: str, config_path: str | None = None):
        self.profile_name = profile_name
        self.root_path = find_skill_root()

        # Load .env from skill root and (if present) from CWD / its parents.
        load_dotenv(dotenv_path=self.root_path / ".env")
        load_dotenv()  # default search from CWD upward; does not override existing

        if not config_path:
            config_path = self.root_path / "config" / "llm_profiles.yaml"
        else:
            config_path = Path(config_path)

        if not Path(config_path).exists():
            raise FileNotFoundError(f"Config file missing: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            self.full_config = yaml.safe_load(f) or {}

        self.global_settings = self.full_config.get("global", {}) or {}
        self.profiles = self.full_config.get("profiles", {}) or {}

        if profile_name not in self.profiles:
            raise KeyError(f"Profile '{profile_name}' not found in llm_profiles.yaml")

        self.profile = self.profiles[profile_name] or {}

        self.provider = os.environ.get(
            "DEFAULT_PROVIDER",
            self.global_settings.get("default_provider", "anthropic"),
        )

        key_env = {
            "gemini": "GEMINI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
        }
        if self.provider not in key_env:
            raise ValueError(f"Unknown LLM provider: {self.provider}")
        self.api_key = os.environ.get(key_env[self.provider])
        if not self.api_key:
            print(
                f"WARNING: API key for provider '{self.provider}' not found in .env / env.",
                file=sys.stderr,
            )

        self.temperature = self.profile.get("temperature", 0.0)
        self.max_output_tokens = self.profile.get("max_output_tokens", 8192)
        self.json_mode = self.profile.get("json_mode", False)
        self.top_p = self.profile.get("top_p")
        self.request_timeout_seconds = self._read_positive_int(
            os.environ.get("LLM_REQUEST_TIMEOUT_SECONDS"),
            self.global_settings.get("timeout_seconds", 180),
            180,
        )
        self.openai_client_retries = self._read_non_negative_int(
            os.environ.get("LLM_OPENAI_CLIENT_RETRIES"),
            self.global_settings.get("retry_attempts", 1),
            1,
        )
        self.openai_base_url = os.environ.get("OPENAI_BASE_URL") or None

        models_dict = self.profile.get("model", {}) or {}
        self.model_name = self._resolve_primary_model(models_dict)
        self.fallback_models = self._resolve_fallback_models()
        self.model_candidates = [self.model_name, *self.fallback_models]
        self.last_call_meta: dict[str, Any] | None = None

    # -- small int helpers ---------------------------------------------------
    @staticmethod
    def _read_positive_int(value: object, fallback: object, default: int) -> int:
        for candidate in (value, fallback):
            try:
                parsed = int(str(candidate).strip())
                if parsed > 0:
                    return parsed
            except Exception:
                continue
        return default

    @staticmethod
    def _read_non_negative_int(value: object, fallback: object, default: int) -> int:
        for candidate in (value, fallback):
            try:
                parsed = int(str(candidate).strip())
                if parsed >= 0:
                    return parsed
            except Exception:
                continue
        return default

    # -- model resolution ----------------------------------------------------
    def _provider_env_name(self, suffix: str) -> str:
        return f"{self.provider.upper()}_{suffix}"

    def _profile_provider_value(self, raw: object) -> object:
        if isinstance(raw, dict):
            return raw.get(self.provider)
        return raw

    @staticmethod
    def _parse_model_list(raw: object) -> list[str]:
        if raw is None:
            return []
        if isinstance(raw, str):
            return [part.strip() for part in raw.split(",") if part.strip()]
        if isinstance(raw, (list, tuple)):
            return [str(item).strip() for item in raw if str(item).strip()]
        return []

    def _resolve_primary_model(self, models_dict: dict[str, Any]) -> str:
        env_override = os.environ.get(self._provider_env_name("MODEL_OVERRIDE"))
        if env_override is None:
            env_override = os.environ.get(self._provider_env_name("MODEL"))
        profile_model = models_dict.get(self.provider)
        model_name = str((env_override if env_override is not None else profile_model) or "").strip()
        if not model_name:
            raise ValueError(
                f"No model configured for provider '{self.provider}' in profile '{self.profile_name}'."
            )
        return model_name

    def _resolve_fallback_models(self) -> list[str]:
        env_models_raw = os.environ.get(self._provider_env_name("FALLBACK_MODELS"))
        env_model_raw = os.environ.get(self._provider_env_name("FALLBACK_MODEL"))
        if env_models_raw is not None:
            fallback_models = self._parse_model_list(env_models_raw)
        elif env_model_raw is not None:
            fallback_models = self._parse_model_list(env_model_raw)
        else:
            from_profile = self._profile_provider_value(self.profile.get("fallback_models"))
            if from_profile is None:
                from_profile = self._profile_provider_value(self.profile.get("fallback_model"))
            fallback_models = self._parse_model_list(from_profile)

        seen: set[str] = set()
        deduped: list[str] = []
        primary_norm = self.model_name.casefold()
        for model in fallback_models:
            norm = model.casefold()
            if not model or norm == primary_norm or norm in seen:
                continue
            seen.add(norm)
            deduped.append(model)
        return deduped

    # -- response extraction helpers ----------------------------------------
    @staticmethod
    def _extract_openai_text(response: Any) -> str:
        message = response.choices[0].message
        content = message.content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [
                p.get("text", "")
                for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            ]
            if parts:
                return "\n".join(t for t in parts if t)
        return str(content)

    @staticmethod
    def _usage_openai(response: Any) -> dict[str, int | None]:
        u = getattr(response, "usage", None)
        if not u:
            return {}
        details = getattr(u, "completion_tokens_details", None)
        return {
            "prompt_tokens": getattr(u, "prompt_tokens", None),
            "completion_tokens": getattr(u, "completion_tokens", None),
            "total_tokens": getattr(u, "total_tokens", None),
            "reasoning_tokens": getattr(details, "reasoning_tokens", None) if details else None,
        }

    @staticmethod
    def _usage_anthropic(response: Any) -> dict[str, int | None]:
        u = getattr(response, "usage", None)
        if not u:
            return {}
        prompt = getattr(u, "input_tokens", None)
        completion = getattr(u, "output_tokens", None)
        total = None
        if prompt is not None and completion is not None:
            total = prompt + completion
        return {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
            "reasoning_tokens": None,
        }

    @staticmethod
    def _usage_gemini(response: Any) -> dict[str, int | None]:
        u = getattr(response, "usage_metadata", None)
        if not u:
            return {}
        return {
            "prompt_tokens": getattr(u, "prompt_token_count", None),
            "completion_tokens": getattr(u, "candidates_token_count", None),
            "total_tokens": getattr(u, "total_token_count", None),
            "reasoning_tokens": getattr(u, "thoughts_token_count", None),
        }

    @staticmethod
    def _is_retryable_error(exc: Exception) -> bool:
        if isinstance(exc, LLMRetryableError):
            return True
        message = str(exc).casefold()
        markers = (
            "timeout", "timed out", "connection", "rate limit", "429",
            "temporar", "unavailable", "overloaded", "try again", "network",
        )
        return any(m in message for m in markers)

    @staticmethod
    def _is_openai_reasoning_model(model_name: str) -> bool:
        m = model_name.lower()
        return m.startswith(("o1", "o3", "o4", "gpt-5"))

    # -- client construction -------------------------------------------------
    def get_client(self):
        if self.provider == "gemini":
            if not genai:
                raise ImportError("google-genai is not installed.")
            return genai.Client(api_key=self.api_key) if self.api_key else None
        if self.provider == "anthropic":
            if not anthropic:
                raise ImportError("anthropic is not installed.")
            return anthropic.Anthropic(api_key=self.api_key) if self.api_key else None
        if self.provider == "openai":
            if not openai:
                raise ImportError("openai is not installed.")
            if not self.api_key:
                return None
            kwargs: dict[str, Any] = {
                "api_key": self.api_key,
                "timeout": float(self.request_timeout_seconds),
                "max_retries": self.openai_client_retries,
            }
            if self.openai_base_url:
                kwargs["base_url"] = self.openai_base_url
            return openai.OpenAI(**kwargs)
        return None

    # -- generation ----------------------------------------------------------
    def _generate_for_model(
        self,
        client: Any,
        *,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict | None,
        json_mode: bool,
    ) -> dict[str, Any]:
        if self.provider == "gemini":
            from google.genai import types

            cfg = types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=self.temperature,
                max_output_tokens=self.max_output_tokens,
            )
            if self.top_p:
                cfg.top_p = self.top_p
            if json_mode:
                cfg.response_mime_type = "application/json"
                if response_schema:
                    cfg.response_schema = response_schema
            response = client.models.generate_content(
                model=model_name, contents=user_prompt, config=cfg
            )
            return {
                "text": getattr(response, "text", "") or "",
                "finish_reason": None,
                "usage": self._usage_gemini(response),
            }

        if self.provider == "anthropic":
            kwargs = {
                "model": model_name,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
                "max_tokens": self.max_output_tokens,
                "temperature": self.temperature,
            }
            if self.top_p:
                kwargs["top_p"] = self.top_p
            response = client.messages.create(**kwargs)
            parts = [
                getattr(b, "text", "")
                for b in (getattr(response, "content", []) or [])
                if getattr(b, "type", "") == "text"
            ]
            return {
                "text": "\n".join(p for p in parts if p),
                "finish_reason": getattr(response, "stop_reason", None),
                "usage": self._usage_anthropic(response),
            }

        if self.provider == "openai":
            is_reasoning = self._is_openai_reasoning_model(model_name)
            kwargs: dict[str, Any] = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
            if is_reasoning:
                kwargs["max_completion_tokens"] = self.max_output_tokens
            else:
                kwargs["max_tokens"] = self.max_output_tokens
                kwargs["temperature"] = self.temperature
                if self.top_p is not None:
                    kwargs["top_p"] = self.top_p
            if json_mode:
                if response_schema:
                    kwargs["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {"name": "output", "schema": response_schema, "strict": True},
                    }
                else:
                    kwargs["response_format"] = {"type": "json_object"}
            response = client.chat.completions.create(**kwargs)
            finish_reason = None
            if getattr(response, "choices", None):
                finish_reason = getattr(response.choices[0], "finish_reason", None)
            text = self._extract_openai_text(response)
            if not (text or "").strip() and str(finish_reason or "").strip().lower() == "length":
                raise LLMRetryableError("OpenAI returned empty content with finish_reason=length.")
            return {
                "text": text,
                "finish_reason": finish_reason,
                "usage": self._usage_openai(response),
            }

        raise NotImplementedError(f"generate not implemented for {self.provider}")

    def generate_content_with_meta(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict | None = None,
    ) -> dict[str, Any]:
        """Call the configured LLM. Returns text/model/provider/usage/finish_reason.

        Walks the model candidate chain (primary + fallbacks) on retryable
        errors. Raises the last error if all candidates fail.
        """
        client = self.get_client()
        if not client:
            raise RuntimeError(
                f"Cannot initialize client for {self.provider}. Missing API key or SDK."
            )
        json_mode = response_schema is not None or self.json_mode
        last_error: Exception | None = None

        for index, model_name in enumerate(self.model_candidates):
            try:
                payload = self._generate_for_model(
                    client,
                    model_name=model_name,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_schema=response_schema,
                    json_mode=json_mode,
                )
                result = {
                    "text": payload.get("text", ""),
                    "model": model_name,
                    "provider": self.provider,
                    "fallback_used": index > 0,
                    "attempt": index + 1,
                    "finish_reason": payload.get("finish_reason"),
                    "usage": payload.get("usage", {}) or {},
                    "model_chain": list(self.model_candidates),
                }
                self.last_call_meta = result
                return result
            except Exception as exc:
                last_error = exc
                has_next = index < len(self.model_candidates) - 1
                if has_next and self._is_retryable_error(exc):
                    print(
                        f"WARNING: model '{model_name}' failed ({exc}); trying "
                        f"fallback '{self.model_candidates[index + 1]}'.",
                        file=sys.stderr,
                    )
                    continue
                raise
        if last_error is not None:
            raise last_error
        raise RuntimeError("LLM call failed: unknown error")

    def generate_content(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict | None = None,
    ) -> str:
        """Backward-compatible helper that returns only the text."""
        return str(
            self.generate_content_with_meta(system_prompt, user_prompt, response_schema).get("text", "")
        )
