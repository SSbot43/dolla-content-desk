"""Safe local bootstrap for Dolla Content Desk.

Python imports sitecustomize automatically at startup. This file keeps the sibling content engine
current when possible and installs a desk-local OpenAI fallback so article generation still works
even if the local engine copy is older or has uncommitted changes that prevent git pull.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


DESK_DIR = Path(__file__).resolve().parent
ENGINE_DIR = Path(os.environ.get("CONTENT_REPO", DESK_DIR.parent / "dollacasino-content")).resolve()


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        text=True,
        capture_output=True,
        timeout=25,
        check=False,
    )


def _load_local_env() -> None:
    """Load .env before the engine imports so OPENAI_API_KEY is available to the fallback."""
    try:
        from dotenv import load_dotenv
        load_dotenv(DESK_DIR / ".env")
    except Exception:
        pass


def _sync_content_engine() -> None:
    if os.environ.get("DOLLA_SKIP_ENGINE_SYNC", "").strip() == "1":
        return
    if not (ENGINE_DIR / ".git").exists():
        return

    try:
        status = _run("git", "-C", str(ENGINE_DIR), "status", "--porcelain")
        if status.returncode != 0 or status.stdout.strip():
            # Never overwrite local work. The desk-local writer fallback below still works even
            # when this repo cannot be updated.
            return
        _run("git", "-C", str(ENGINE_DIR), "pull", "--ff-only", "--quiet")
    except Exception:
        return


def _openai_text(prompt: str) -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set in the Content Desk .env file")

    try:
        from openai import OpenAI, APIConnectionError, APIStatusError, RateLimitError
    except ImportError as e:
        raise RuntimeError("OpenAI package is not installed; restart with the BAT file so requirements install") from e

    client = OpenAI(api_key=key)
    model = os.environ.get("OPENAI_MODEL", "gpt-5.6-luna").strip() or "gpt-5.6-luna"
    last: Exception | None = None

    for attempt in range(3):
        try:
            response = client.responses.create(model=model, input=prompt)
            text = (getattr(response, "output_text", "") or "").strip()
            if text:
                return text
            last = RuntimeError("OpenAI returned an empty article")
            break
        except RateLimitError as e:
            last = e
            time.sleep(4 * (attempt + 1))
        except APIConnectionError as e:
            last = e
            time.sleep(3 * (attempt + 1))
        except APIStatusError as e:
            last = e
            if getattr(e, "status_code", 0) >= 500:
                time.sleep(4 * (attempt + 1))
                continue
            break
        except Exception as e:
            last = e
            break

    raise RuntimeError(f"OpenAI fallback failed: {last}")


def _install_writer_fallback() -> None:
    """Patch any local engine generation version so Gemini failure automatically uses OpenAI."""
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        return

    src = ENGINE_DIR / "src"
    if not src.exists():
        return
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    try:
        from dolla_content import generate as gen
    except Exception:
        return

    # If this interpreter already has our wrapper, leave it alone.
    if getattr(gen, "_dolla_desk_openai_fallback", False):
        return

    original_gemini = getattr(gen, "_call_gemini", None)
    if not callable(original_gemini):
        return

    def gemini_then_openai(prompt: str) -> str:
        try:
            return original_gemini(prompt)
        except Exception as gemini_error:
            try:
                return _openai_text(prompt)
            except Exception as openai_error:
                raise RuntimeError(
                    f"Gemini failed ({gemini_error}); OpenAI fallback also failed ({openai_error})"
                ) from openai_error

    gen._call_gemini = gemini_then_openai
    gen._dolla_desk_openai_fallback = True


_load_local_env()
_sync_content_engine()
_install_writer_fallback()
