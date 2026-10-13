"""Thin Gemini client (REST, standard library only) behind a small interface.

Tests and local demos inject a fake that implements `generate`; nothing else in the app
knows which model or vendor is used.

Resilience (each step logged with Google's reason, never the user's text):
- HTTP 400 with a schema   -> retry once in plain JSON mode (schema described in the prompt).
- HTTP 401 (key type)      -> retry once with the key as a Bearer token (newer "AQ." keys).
- HTTP 404 (unknown model) -> retry once with FALLBACK_MODEL.
- endpoint "auto": AI Studio first; on 401/402/403 try Vertex AI / Agent Platform (keys made in
  the Cloud console, billed to the project's Google Cloud credits).
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Protocol, Tuple

log = logging.getLogger("app.assistant")

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
VERTEX_URL = "https://aiplatform.googleapis.com/v1/publishers/google/models/{model}:generateContent"
ENDPOINTS = ("ai_studio", "vertex")
FALLBACK_MODEL = "gemini-2.5-flash"


class LLMError(RuntimeError):
    """The model could not be reached or returned something unusable."""

    def __init__(self, message: str, status: Optional[int] = None, detail: str = ""):
        super().__init__(message)
        self.status = status
        self.detail = detail


class LLM(Protocol):
    def generate(self, *, system: str, history: List[Dict[str, str]], schema: Dict[str, Any]) -> Dict[str, Any]:
        """history: [{"role": "user"|"assistant", "text": ...}], oldest first, ending with the user turn.
        Returns the parsed JSON object the model produced."""


class GeminiLLM:
    def __init__(self, api_key: str, model: str, timeout: float = 60.0, endpoint: str = "auto"):
        self.api_key = api_key.strip()
        self.model = model.strip()
        self.timeout = timeout
        self.use_bearer = False  # flipped on after a 401 so later calls go straight to what works
        self.endpoint = endpoint if endpoint in ENDPOINTS else "ai_studio"
        self.auto = endpoint not in ENDPOINTS  # may switch endpoint once on an auth/billing error

    # -------------------------------------------------------------- request building
    @staticmethod
    def _contents(history: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        contents = []
        for m in history:
            role = "user" if m["role"] == "user" else "model"
            if not contents and role == "model":
                continue  # Gemini expects the conversation to open with a user turn
            contents.append({"role": role, "parts": [{"text": m["text"]}]})
        return contents

    def _body(self, system: str, history, schema: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        config: Dict[str, Any] = {"responseMimeType": "application/json"}
        if schema is not None:
            config["responseSchema"] = schema
        else:
            system = system + "\n\nReply ONLY with a JSON object of the form {\"draft\": {...same keys as CURRENT DRAFT...}, \"reply\": \"...\"}."
        return {"systemInstruction": {"parts": [{"text": system}]}, "contents": self._contents(history),
                "generationConfig": config}

    def _post(self, model: str, body: Dict[str, Any], bearer: bool, endpoint: str = "ai_studio") -> Dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        url = (VERTEX_URL if endpoint == "vertex" else GEMINI_URL).format(model=model)
        if bearer:
            headers["Authorization"] = f"Bearer {self.api_key}"
        else:
            headers["x-goog-api-key"] = self.api_key
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:600].decode(errors="replace")
            raise LLMError(f"model returned HTTP {exc.code}", exc.code, detail) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LLMError(f"model unreachable: {exc}") from exc

    # -------------------------------------------------------------- public
    def generate(self, *, system: str, history: List[Dict[str, str]], schema: Dict[str, Any]) -> Dict[str, Any]:
        model, use_schema, bearer, endpoint = self.model, True, self.use_bearer, self.endpoint
        tried: List[Tuple[str, bool, bool, str]] = []
        while True:
            tried.append((model, use_schema, bearer, endpoint))
            try:
                payload = self._post(model, self._body(system, history, schema if use_schema else None), bearer, endpoint)
                self.use_bearer, self.endpoint = bearer, endpoint
                if model != self.model:
                    log.warning("Gemini model %r failed; using %r instead. Set GEMINI_MODEL to silence this.", self.model, model)
                return parse_response(payload)
            except LLMError as exc:
                log.warning("Gemini call failed (endpoint=%s, model=%s, schema=%s, bearer=%s): %s %s",
                            endpoint, model, use_schema, bearer, exc, exc.detail.replace("\n", " ")[:400])
                nxt = None
                if self.auto and endpoint == "ai_studio" and exc.status in (401, 402, 403):
                    nxt = (model, use_schema, False, "vertex")
                elif exc.status == 401 and not bearer:
                    nxt = (model, use_schema, True, endpoint)
                elif exc.status == 404 and model != FALLBACK_MODEL:
                    nxt = (FALLBACK_MODEL, use_schema, bearer, endpoint)
                elif exc.status == 400 and use_schema:
                    nxt = (model, False, bearer, endpoint)
                elif exc.status is None and "invalid JSON" in str(exc) and use_schema:
                    nxt = (model, False, bearer, endpoint)
                if nxt is None or nxt in tried:
                    raise
                model, use_schema, bearer, endpoint = nxt


def parse_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    candidates = payload.get("candidates") or []
    if not candidates:
        reason = (payload.get("promptFeedback") or {}).get("blockReason")
        raise LLMError(f"no answer from model{f' ({reason})' if reason else ''}")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    if text.startswith("```"):  # tolerate fenced JSON in plain JSON mode
        text = text.strip("`")
        text = text[text.find("{"):]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError("model returned invalid JSON", detail=text[:200]) from exc
    if not isinstance(data, dict):
        raise LLMError("model returned unexpected JSON")
    return data


def make_llm(api_key: str, model: str, endpoint: str = "auto") -> Optional[LLM]:
    return GeminiLLM(api_key, model, endpoint=endpoint) if api_key.strip() else None
