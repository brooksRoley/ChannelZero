"""Practice reflection — sentiment + a one-line mirror for an in-session prompt.

Stateless by design: the reflection text is sent to the LLM and the result is
returned, but nothing is stored or logged (the practice journal lives on the
device, like the journal). Public so the logged-out hypnosis toys can use it;
the client falls back to an on-device lexicon whenever this returns non-200.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..llm.chat import chat_completion, llm_configured
from ..ratelimit import limiter

router = APIRouter()
logger = logging.getLogger(__name__)

Method = Literal["zeromind", "spiral", "audio", "studio", "trance"]
Moment = Literal["before", "during", "after"]

METHOD_NAMES = {
    "zeromind": "a breath-paced binaural descent",
    "spiral": "a visual fixation spiral",
    "audio": "an adaptive entrainment audio journey",
    "studio": "authoring a subliminal video in the glass studio",
    "trance": "a star-tunnel breath journey",
}


class ReflectRequest(BaseModel):
    method: Method
    moment: Moment
    prompt: str = Field(max_length=200)
    text: str = Field(min_length=1, max_length=600)
    # Optional 1–5 felt-sense ratings, so the mirror can name the shift.
    before: int | None = Field(default=None, ge=1, le=5)
    after: int | None = Field(default=None, ge=1, le=5)


class ReflectResponse(BaseModel):
    valence: float  # -1 (heavy) .. 1 (light)
    energy: float  # 0 (still) .. 1 (charged)
    tone: str  # one lowercase word
    reflection: str  # ≤ 2 short sentences
    source: Literal["llm"] = "llm"


def build_prompt(body: ReflectRequest) -> str:
    shift = ""
    if body.before is not None and body.after is not None:
        shift = f"\nThey rated how they felt {body.before}/5 before and {body.after}/5 after."
    return f"""You are a calm, plain-spoken practice guide inside a self-hypnosis app.
Someone is {body.moment} {METHOD_NAMES[body.method]}. They were asked: "{body.prompt}"
They wrote: "{body.text}"{shift}

Return ONLY a JSON object, no prose, with these keys:
- "valence": number from -1 (heavy, distressed) to 1 (light, at ease)
- "energy": number from 0 (still, sleepy) to 1 (activated, restless)
- "tone": one lowercase word naming their state (e.g. "settling", "restless", "tender")
- "reflection": at most two short sentences that mirror back what they noticed in their own words and offer one small, concrete cue for the next minute of practice. No praise, no diagnosis, no exclamation marks, no mention of being an AI.
If they describe being in danger or wanting to harm themselves, set "tone" to "unsafe" and make the reflection a gentle suggestion to pause and reach out to someone they trust or a local crisis line."""


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_reply(raw: str) -> ReflectResponse:
    """Pull the first JSON object out of the reply and clamp it into shape."""
    match = _JSON_RE.search(raw or "")
    if not match:
        raise ValueError("no JSON object in reply")
    data = json.loads(match.group(0))

    def num(key: str, lo: float, hi: float) -> float:
        v = float(data.get(key, 0))
        return max(lo, min(hi, v))

    tone = re.sub(r"[^a-z\-]", "", str(data.get("tone", "")).lower())[:24] or "present"
    reflection = " ".join(str(data.get("reflection", "")).split())[:280]
    if not reflection:
        raise ValueError("empty reflection")
    return ReflectResponse(
        valence=num("valence", -1, 1),
        energy=num("energy", 0, 1),
        tone=tone,
        reflection=reflection,
    )


@router.post("/reflect", response_model=ReflectResponse)
@limiter.limit("20/hour")
async def reflect(request: Request, body: ReflectRequest):
    if not llm_configured():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Reflection LLM not configured")
    raw = await chat_completion(build_prompt(body), max_tokens=220, timeout=20.0)
    try:
        return parse_reply(raw)
    except (ValueError, TypeError, json.JSONDecodeError):
        # Never log the user's text — only that the shape was wrong.
        logger.warning("practice.reflect: unparseable LLM reply (%d chars)", len(raw or ""))
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Reflection reply was malformed")
