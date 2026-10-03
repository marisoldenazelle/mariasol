"""
Client LLM sous contrainte.

Le LLM est utilisé exclusivement comme *parseur structuré* : on lui impose un
schéma Pydantic, on valide la sortie, et on rejette tout ce qui n'est pas
conforme. Aucune sortie libre n'est jamais consommée par la logique métier.

Trois fournisseurs :
  - albert            : API Albert (DINUM), compatible OpenAI, SecNumCloud
  - openai_compatible : tout endpoint compatible OpenAI (LLM interne, Ollama…)
  - offline           : aucun appel réseau — les fonctions d'analyse basculent
                        automatiquement sur leurs heuristiques déterministes
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from datetime import datetime, timezone
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from .config import settings

T = TypeVar("T", bound=BaseModel)

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


class LLMUnavailable(RuntimeError):
    """Le fournisseur LLM n'est pas configuré ou injoignable."""


class LLMInvalidOutput(RuntimeError):
    """Le modèle n'a pas produit de sortie conforme au schéma après N essais."""


# ---------------------------------------------------------------------------
# Journal d'audit
# ---------------------------------------------------------------------------

def _audit(db_path: str, model: str, schema: str, prompt: str,
           ok: bool, latency_ms: int, error: str = "") -> None:
    if not settings.audit_log:
        return
    try:
        con = sqlite3.connect(db_path, timeout=10)
        con.execute(
            """CREATE TABLE IF NOT EXISTS llm_audit (
                   ts TEXT, model TEXT, schema TEXT, prompt_sha256 TEXT,
                   prompt_chars INTEGER, ok INTEGER, latency_ms INTEGER, error TEXT)"""
        )
        con.execute(
            "INSERT INTO llm_audit VALUES (?,?,?,?,?,?,?,?)",
            (
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                model,
                schema,
                hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                len(prompt),
                int(ok),
                latency_ms,
                error[:500],
            ),
        )
        con.commit()
        con.close()
    except Exception:
        pass  # l'audit ne doit jamais faire échouer un traitement


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class LLMClient:
    def __init__(self) -> None:
        self.provider = settings.llm_provider
        self.model = settings.llm_model
        self._client = None

    # -- infrastructure -----------------------------------------------------
    @property
    def available(self) -> bool:
        return settings.llm_available

    def _openai(self):
        if self._client is None:
            if not self.available:
                raise LLMUnavailable(
                    "Aucun fournisseur LLM configuré "
                    "(définir ALBERT_API_KEY ou REGWATCH_LLM_PROVIDER=offline)."
                )
            from openai import OpenAI

            self._client = OpenAI(
                base_url=settings.albert_base_url,
                api_key=settings.albert_api_key or "not-needed",
                timeout=settings.llm_timeout,
                max_retries=0,  # on gère nos propres réessais avec feedback
            )
        return self._client

    def list_models(self) -> list[str]:
        """Découverte des modèles exposés par l'endpoint (page Administration)."""
        try:
            return sorted(m.id for m in self._openai().models.list().data)
        except Exception as exc:  # pragma: no cover
            raise LLMUnavailable(str(exc)) from exc

    def ping(self) -> tuple[bool, str]:
        try:
            models = self.list_models()
            ok = self.model in models
            msg = (
                f"Connexion établie · {len(models)} modèles exposés."
                + ("" if ok else f" ⚠ « {self.model} » absent de la liste.")
            )
            return True, msg
        except Exception as exc:
            return False, str(exc)

    # -- appel structuré ----------------------------------------------------
    def structured(
        self,
        schema: type[T],
        system: str,
        user: str,
        max_tokens: int = 1200,
    ) -> T:
        """Appelle le modèle et renvoie une instance validée de `schema`.

        La sortie est revalidée à chaque essai ; en cas d'échec, l'erreur de
        validation est réinjectée au modèle. Après épuisement des essais, on
        lève : jamais de repli silencieux sur une sortie approximative.
        """
        client = self._openai()
        json_schema = schema.model_json_schema()
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": (
                    f"{user}\n\n"
                    "Réponds UNIQUEMENT par un objet JSON valide, sans texte autour, "
                    "conforme au schéma suivant :\n"
                    f"{json.dumps(json_schema, ensure_ascii=False)}"
                ),
            },
        ]

        last_error = ""
        started = time.monotonic()
        for attempt in range(settings.llm_max_retries + 1):
            try:
                resp = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=settings.llm_temperature,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                )
                raw = (resp.choices[0].message.content or "").strip()
            except Exception as exc:
                # certains endpoints refusent response_format : nouvel essai sans.
                # Ce second appel doit être protégé comme le premier : une
                # coupure réseau à cet instant remontait une exception brute
                # (ConnectionError) que les appelants n'attrapent pas, et une
                # analyse de trois cents contributions s'arrêtait sur une
                # trace Python.
                erreur: Exception | None = exc
                if "response_format" in str(exc) and attempt == 0:
                    try:
                        resp = client.chat.completions.create(
                            model=self.model,
                            messages=messages,
                            temperature=settings.llm_temperature,
                            max_tokens=max_tokens,
                        )
                        raw = (resp.choices[0].message.content or "").strip()
                        erreur = None
                    except Exception as exc_repli:
                        erreur = exc_repli
                if erreur is not None:
                    last_error = f"{type(erreur).__name__}: {erreur}"
                    if attempt == settings.llm_max_retries:
                        _audit(settings.db_path, self.model, schema.__name__, user,
                               False, int((time.monotonic() - started) * 1000), last_error)
                        raise LLMUnavailable(last_error) from erreur
                    time.sleep(1.5 * (attempt + 1))
                    continue

            block = _JSON_BLOCK.search(raw)
            try:
                if not block:
                    raise ValueError("aucun objet JSON dans la réponse")
                obj = schema.model_validate_json(block.group(0))
                _audit(settings.db_path, self.model, schema.__name__, user, True,
                       int((time.monotonic() - started) * 1000))
                return obj
            except (ValidationError, ValueError) as exc:
                last_error = str(exc)[:800]
                messages.append({"role": "assistant", "content": raw[:2000]})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Sortie non conforme au schéma. Erreur de validation :\n"
                            f"{last_error}\n"
                            "Renvoie uniquement le JSON corrigé."
                        ),
                    }
                )

        _audit(settings.db_path, self.model, schema.__name__, user, False,
               int((time.monotonic() - started) * 1000), last_error)
        raise LLMInvalidOutput(
            f"Sortie non conforme après {settings.llm_max_retries + 1} essais : {last_error}"
        )


_client: LLMClient | None = None


def get_client() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client


def reset_client() -> None:
    """À appeler après une modification de configuration en cours de session."""
    global _client
    _client = None
