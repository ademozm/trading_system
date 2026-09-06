"""
Katman 3c — Birleşik LLM İstemcisi
=====================================
TradingAgents/Vibe-Trading'in "çoklu LLM sağlayıcı" esnekliğinden ilham
alınarak, ajan düğümlerinin (nodes.py) hangi sağlayıcıyı kullandığını
bilmesine gerek kalmadan tek bir `complete(system, user) -> str` arayüzü
sunar.

Üç somut istemci:
  - OpenAICompatibleClient: OpenAI, DeepSeek, Qwen, yerel Ollama/LM Studio
    gibi OpenAI-uyumlu HER endpoint için (base_url parametresiyle).
  - AnthropicClient: Claude modelleri için.
  - MockLLMClient: **gerçek API çağrısı yapmaz** — birim testlerinde ve bu
    geliştirme ortamında (internet erişimi kapalı) zincirin uçtan uca
    doğru bağlandığını doğrulamak için kullanılır. Asla canlıda
    kullanılmamalıdır.
"""

from __future__ import annotations

import abc
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class LLMClient(abc.ABC):
    """Tüm sağlayıcıların uyması gereken minimal arayüz."""

    @abc.abstractmethod
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Sistem + kullanıcı promptunu alır, modelin ürettiği ham metni döndürür."""
        raise NotImplementedError


class OpenAICompatibleClient(LLMClient):
    """OpenAI SDK'sını kullanan, base_url ile herhangi bir uyumlu endpoint'e
    yönlendirilebilen istemci (OpenAI, DeepSeek, Qwen, Ollama, LM Studio...)."""

    def __init__(self, api_key: str, model: str, base_url: Optional[str] = None, temperature: float = 0.3) -> None:
        try:
            from openai import OpenAI
        except ImportError as e:  # pragma: no cover
            raise ImportError("openai paketi kurulu değil: `pip install openai`") from e

        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.temperature = temperature

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or ""


class AnthropicClient(LLMClient):
    """Claude modelleri için istemci."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6", max_tokens: int = 1500) -> None:
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover
            raise ImportError("anthropic paketi kurulu değil: `pip install anthropic`") from e

        self._client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text_blocks = [block.text for block in response.content if block.type == "text"]
        return "\n".join(text_blocks)


class MockLLMClient(LLMClient):
    """
    Gerçek bir API'ye bağlanmaz. `responder` fonksiyonu, gelen
    (system_prompt, user_prompt) çiftine göre sabit/kurallı bir yanıt
    üretir. Varsayılan davranış: rol ismine göre basit, tutarlı
    şablon yanıtlar döndürmek (nodes.py'nin JSON ayrıştırma mantığını
    test edebilmek için).

    KULLANIM UYARISI: Bu istemci sadece test/geliştirme içindir.
    Gerçek bir yatırım kararı asla MockLLMClient çıktısına dayanmamalıdır.
    """

    def __init__(self, responder: Optional[Callable[[str, str], str]] = None) -> None:
        self.responder = responder or self._default_responder
        self.call_log: list[tuple[str, str]] = []

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.call_log.append((system_prompt, user_prompt))
        return self.responder(system_prompt, user_prompt)

    @staticmethod
    def _default_responder(system_prompt: str, user_prompt: str) -> str:
        # Trader düğümü JSON bekliyor; diğer düğümler serbest metin bekliyor.
        if "JSON" in system_prompt or "json" in system_prompt:
            return '{"side": "long", "confidence": 0.55, "rationale": "Mock trader yanıtı (test amaçlı)."}'
        return "Bu, geliştirme ortamında üretilmiş bir mock (sahte) analist yanıtıdır."


def build_llm_client(
    provider: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
) -> LLMClient:
    """
    Konfigürasyondan (main.py veya bir config dosyasından) tek bir
    fonksiyonla istemci oluşturmak için yardımcı fabrika.

    provider: "openai" | "anthropic" | "mock"
    """
    if provider == "mock":
        return MockLLMClient()
    if provider == "openai":
        if not api_key or not model:
            raise ValueError("provider='openai' için api_key ve model zorunludur.")
        return OpenAICompatibleClient(api_key=api_key, model=model, base_url=base_url)
    if provider == "anthropic":
        if not api_key or not model:
            raise ValueError("provider='anthropic' için api_key ve model zorunludur.")
        return AnthropicClient(api_key=api_key, model=model)
    raise ValueError(f"Bilinmeyen provider: {provider} (openai | anthropic | mock olmalı)")
