import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


try:
    from dotenv import load_dotenv

    ROOT_DIR = Path(__file__).resolve().parents[2]
    load_dotenv(ROOT_DIR / ".env")
    load_dotenv(ROOT_DIR / "backend" / ".env")
except Exception:
    pass


DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")


def _json_request(url: str, payload: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None, timeout: int = 25) -> Dict[str, Any]:
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=data,
        headers=headers or {},
        method="POST" if payload is not None else "GET",
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw)


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None

    stripped = text.strip()

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass

    start = stripped.find("{")
    end = stripped.rfind("}")

    if start != -1 and end != -1 and end > start:
        candidate = stripped[start:end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            return None

    return None


def get_llm_status() -> Dict[str, Any]:
    ollama_running = False
    ollama_models = []

    try:
        result = _json_request(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        ollama_running = True
        ollama_models = [item.get("name") for item in result.get("models", [])]
    except Exception:
        ollama_running = False

    return {
        "default_provider": DEFAULT_PROVIDER,
        "providers": {
            "ollama": {
                "configured": True,
                "running": ollama_running,
                "base_url": OLLAMA_BASE_URL,
                "model": OLLAMA_MODEL,
                "available_models": ollama_models,
            },
            "openai": {
                "configured": bool(OPENAI_API_KEY),
                "model": OPENAI_MODEL,
            },
            "gemini": {
                "configured": bool(GEMINI_API_KEY),
                "model": GEMINI_MODEL,
            },
        },
    }


def _call_ollama(prompt: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        response = _json_request(
            f"{OLLAMA_BASE_URL}/api/generate",
            payload={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
            },
            headers={"Content-Type": "application/json"},
            timeout=45,
        )
        return response.get("response", ""), None
    except Exception as exc:
        return None, f"Ollama call failed: {exc}"


def _call_openai(system_prompt: str, user_prompt: str) -> Tuple[Optional[str], Optional[str]]:
    if not OPENAI_API_KEY:
        return None, "OPENAI_API_KEY is missing."

    try:
        response = _json_request(
            "https://api.openai.com/v1/chat/completions",
            payload={
                "model": OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.8,
                "response_format": {"type": "json_object"},
            },
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {OPENAI_API_KEY}",
            },
            timeout=45,
        )

        content = response["choices"][0]["message"]["content"]
        return content, None
    except Exception as exc:
        return None, f"OpenAI call failed: {exc}"


def _call_gemini(system_prompt: str, user_prompt: str) -> Tuple[Optional[str], Optional[str]]:
    if not GEMINI_API_KEY:
        return None, "GEMINI_API_KEY is missing."

    try:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        )

        response = _json_request(
            url,
            payload={
                "contents": [
                    {
                        "parts": [
                            {
                                "text": f"{system_prompt}\n\n{user_prompt}\n\nReturn only valid JSON."
                            }
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.8,
                    "responseMimeType": "application/json",
                },
            },
            headers={"Content-Type": "application/json"},
            timeout=45,
        )

        content = response["candidates"][0]["content"]["parts"][0]["text"]
        return content, None
    except Exception as exc:
        return None, f"Gemini call failed: {exc}"


def generate_json_with_llm(system_prompt: str, user_prompt: str, provider: Optional[str] = None) -> Dict[str, Any]:
    selected_provider = (provider or DEFAULT_PROVIDER or "ollama").lower()

    full_prompt = (
        f"{system_prompt}\n\n"
        f"{user_prompt}\n\n"
        "Return only one valid JSON object. Do not include markdown."
    )

    if selected_provider == "off":
        return {
            "ok": False,
            "provider": "off",
            "data": None,
            "error": "LLM provider is off.",
        }

    if selected_provider == "openai":
        text, error = _call_openai(system_prompt, user_prompt)
    elif selected_provider == "gemini":
        text, error = _call_gemini(system_prompt, user_prompt)
    else:
        selected_provider = "ollama"
        text, error = _call_ollama(full_prompt)

    if error:
        return {
            "ok": False,
            "provider": selected_provider,
            "data": None,
            "error": error,
        }

    parsed = _extract_json_object(text or "")

    if parsed is None:
        return {
            "ok": False,
            "provider": selected_provider,
            "data": None,
            "error": "LLM returned text, but no valid JSON object could be parsed.",
            "raw": text,
        }

    return {
        "ok": True,
        "provider": selected_provider,
        "data": parsed,
        "error": None,
    }
