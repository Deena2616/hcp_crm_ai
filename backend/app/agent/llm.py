"""
Thin wrapper around Groq's chat completion API.

Primary model: gemma2-9b-it (fast, cheap - used for most extraction/summarization tasks)
Fallback model: llama-3.3-70b-versatile (used when a task needs stronger reasoning,
e.g. ambiguous intent routing, or if the primary model call fails)
"""
import json
from groq import Groq
from app.config import settings

_client = Groq(api_key=settings.groq_api_key) if settings.groq_api_key else None


def _get_client():
    global _client
    if _client is None:
        _client = Groq(api_key=settings.groq_api_key)
    return _client


def call_llm(system_prompt: str, user_prompt: str, use_fallback: bool = False,
             json_mode: bool = False, temperature: float = 0.2) -> str:
    """Call Groq chat completion. Returns raw text content."""
    client = _get_client()
    model = settings.groq_fallback_model if use_fallback else settings.groq_model

    kwargs = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    try:
        completion = client.chat.completions.create(**kwargs)
        return completion.choices[0].message.content
    except Exception as e:
        if not use_fallback:
            # retry once with the stronger fallback model
            return call_llm(system_prompt, user_prompt, use_fallback=True,
                             json_mode=json_mode, temperature=temperature)
        raise RuntimeError(f"Groq LLM call failed: {e}")


def call_llm_json(system_prompt: str, user_prompt: str, use_fallback: bool = False) -> dict:
    """Call the LLM and parse a JSON object from the response, with a safe fallback."""
    raw = call_llm(system_prompt, user_prompt, use_fallback=use_fallback, json_mode=True)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Strip markdown fences if the model added them despite json_mode
        cleaned = raw.strip().strip("```json").strip("```").strip()
        try:
            return json.loads(cleaned)
        except Exception:
            return {"_parse_error": True, "raw": raw}
