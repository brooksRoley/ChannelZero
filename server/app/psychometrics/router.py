from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, Any

from ..auth.deps import get_current_user_id
from ..db import get_pool
from ..ratelimit import limiter
from .scoring import generate_psycho_profile, encrypt_responses
from .question_pool import get_next_item, get_next_items, CORE_POOL
from ..llm.psychoanalysis import generate_psychoanalysis_narrative

router = APIRouter()

class AssessmentPayload(BaseModel):
    responses: Dict[str, Any]

class MicrodosePayload(BaseModel):
    item_id: str
    value: int
    connector_context: str | None = None
    trance_coherence: float | None = None
    session_duration_ms: int | None = None

@router.post("/submit")
async def submit_assessment(payload: AssessmentPayload, user_id: UUID = Depends(get_current_user_id)):
    """Accept the multi-part assessment and store the scored results."""
    pool = get_pool()

    profile = generate_psycho_profile(payload.responses)
    encrypted_raw = encrypt_responses(payload.responses)

    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO user_psychometrics 
                (user_id, scorable_responses, ipip_neo_scores, ecr_r_scores, 
                 love_language, sociosexual_orientation, values_cluster, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, now())
            ON CONFLICT (user_id) DO UPDATE SET
                scorable_responses = EXCLUDED.scorable_responses,
                ipip_neo_scores = EXCLUDED.ipip_neo_scores,
                ecr_r_scores = EXCLUDED.ecr_r_scores,
                love_language = EXCLUDED.love_language,
                sociosexual_orientation = EXCLUDED.sociosexual_orientation,
                values_cluster = EXCLUDED.values_cluster,
                updated_at = now()
        """, 
        str(user_id), 
        encrypted_raw, 
        json.dumps(profile["ipip_neo_scores"]), 
        json.dumps(profile["ecr_r_scores"]), 
        profile["love_language"], 
        profile["sociosexual_orientation"], 
        profile["values_cluster"])
        
    return {"status": "success", "profile": profile}

@router.get("/profile")
async def get_my_profile(user_id: UUID = Depends(get_current_user_id)):
    """Fetch the user's computed psychometric profile."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT ipip_neo_scores, ecr_r_scores, love_language, sociosexual_orientation, values_cluster, narrative
            FROM user_psychometrics
            WHERE user_id = $1
        """, str(user_id))
    
    if not row:
        raise HTTPException(status_code=404, detail="No psychometric profile found.")

    return {
        "ipip_neo_scores": json.loads(row["ipip_neo_scores"]) if isinstance(row["ipip_neo_scores"], str) else row["ipip_neo_scores"],
        "ecr_r_scores": json.loads(row["ecr_r_scores"]) if isinstance(row["ecr_r_scores"], str) else row["ecr_r_scores"],
        "love_language": row["love_language"],
        "sociosexual_orientation": row["sociosexual_orientation"],
        "values_cluster": row["values_cluster"],
        "narrative": row["narrative"]
    }

@router.post("/narrative")
@limiter.limit("5/hour")
async def generate_narrative(request: Request, user_id: UUID = Depends(get_current_user_id)):
    """Triggers the LLM psychoanalysis based on current scores."""
    pool = get_pool()
    
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT ipip_neo_scores, ecr_r_scores, love_language, sociosexual_orientation, values_cluster
            FROM user_psychometrics
            WHERE user_id = $1
        """, str(user_id))
        
    if not row:
        raise HTTPException(status_code=404, detail="No profile found to analyze. Please submit the assessment first.")
        
    profile_data = {
        "ipip_neo_scores": json.loads(row["ipip_neo_scores"]) if isinstance(row["ipip_neo_scores"], str) else row["ipip_neo_scores"],
        "ecr_r_scores": json.loads(row["ecr_r_scores"]) if isinstance(row["ecr_r_scores"], str) else row["ecr_r_scores"],
        "love_language": row["love_language"],
        "sociosexual_orientation": row["sociosexual_orientation"],
        "values_cluster": row["values_cluster"]
    }
    
    narrative = await generate_psychoanalysis_narrative(user_id, profile_data)
    
    async with pool.acquire() as conn:
        await conn.execute("UPDATE user_psychometrics SET narrative = $1 WHERE user_id = $2", narrative, str(user_id))
        
    return {"status": "success", "narrative": narrative}

@router.delete("/profile")
async def delete_my_profile(user_id: UUID = Depends(get_current_user_id)):
    """Allow users to delete their psychometric data for privacy."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM user_psychometrics WHERE user_id = $1", str(user_id))
    return {"status": "success", "message": "Psychometric data deleted."}


@router.post("/microdose", status_code=204)
async def submit_microdose(
    payload: MicrodosePayload,
    user_id: UUID = Depends(get_current_user_id),
):
    """Store a single psychometric item response and recompute scores if instrument is complete."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO psychometric_responses (user_id, item_id, value, connector_context, trance_coherence, session_duration_ms)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (user_id, item_id) DO UPDATE SET
                value = EXCLUDED.value,
                connector_context = EXCLUDED.connector_context,
                trance_coherence = EXCLUDED.trance_coherence,
                session_duration_ms = EXCLUDED.session_duration_ms,
                created_at = now()
            """,
            str(user_id), payload.item_id, payload.value,
            payload.connector_context, payload.trance_coherence, payload.session_duration_ms,
        )

        # Check if we can auto-compute scores
        rows = await conn.fetch(
            "SELECT item_id, value FROM psychometric_responses WHERE user_id = $1",
            str(user_id),
        )
        answered = {r["item_id"]: r["value"] for r in rows}

        # Try to build IPIP-NEO scores (need all 10 core items)
        ipip_ids = [f"ipip_neo_{i}" for i in range(10)]
        ipip_values = [answered[iid] for iid in ipip_ids if iid in answered]

        # Try to build ECR-R scores (need all 4 core items)
        ecr_ids = [f"ecr_r_{i}" for i in range(4)]
        ecr_values = [answered[iid] for iid in ecr_ids if iid in answered]

        # Extract identity items
        love_language = None
        values_cluster = None
        sociosexual = None

        # For categorical items, value is the index into the options list
        pool_map = {item["item_id"]: item for item in CORE_POOL}

        if "identity_love_language" in answered:
            item = pool_map["identity_love_language"]
            idx = answered["identity_love_language"]
            love_language = item["options"][idx] if item["options"] and 0 <= idx < len(item["options"]) else None

        if "identity_values" in answered:
            item = pool_map["identity_values"]
            idx = answered["identity_values"]
            values_cluster = item["options"][idx] if item["options"] and 0 <= idx < len(item["options"]) else None

        if "identity_sociosexual" in answered:
            item = pool_map["identity_sociosexual"]
            idx = answered["identity_sociosexual"]
            sociosexual = item["options"][idx] if item["options"] and 0 <= idx < len(item["options"]) else None

        # Compute available scores
        ipip_scores = None
        if len(ipip_values) >= 10:
            from .scoring import _score_ocean_items
            ipip_scores = _score_ocean_items(ipip_values)

        ecr_scores = None
        if len(ecr_values) >= 4:
            from .scoring import _score_ecr_r_items, classify_attachment_style
            ecr_scores = _score_ecr_r_items(ecr_values)
            ecr_scores["attachment_style"] = classify_attachment_style(
                ecr_scores["anxiety"], ecr_scores["avoidance"]
            )

        # Upsert into user_psychometrics if we have anything to store
        if ipip_scores or ecr_scores or love_language or values_cluster or sociosexual:
            await conn.execute(
                """
                INSERT INTO user_psychometrics
                    (user_id, ipip_neo_scores, ecr_r_scores, love_language, sociosexual_orientation, values_cluster, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, now())
                ON CONFLICT (user_id) DO UPDATE SET
                    ipip_neo_scores = COALESCE(EXCLUDED.ipip_neo_scores, user_psychometrics.ipip_neo_scores),
                    ecr_r_scores = COALESCE(EXCLUDED.ecr_r_scores, user_psychometrics.ecr_r_scores),
                    love_language = COALESCE(EXCLUDED.love_language, user_psychometrics.love_language),
                    sociosexual_orientation = COALESCE(EXCLUDED.sociosexual_orientation, user_psychometrics.sociosexual_orientation),
                    values_cluster = COALESCE(EXCLUDED.values_cluster, user_psychometrics.values_cluster),
                    updated_at = now()
                """,
                str(user_id),
                json.dumps(ipip_scores) if ipip_scores else None,
                json.dumps(ecr_scores) if ecr_scores else None,
                love_language,
                sociosexual,
                values_cluster,
            )


@router.get("/progress")
async def get_progress(user_id: UUID = Depends(get_current_user_id)):
    """Return all answered psychometric item IDs, values, and whether they came from microdose (trance)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT item_id, value, connector_context FROM psychometric_responses WHERE user_id = $1",
            str(user_id),
        )
    answered = {
        r["item_id"]: {
            "value": r["value"],
            "from_trance": r["connector_context"] is not None,
        }
        for r in rows
    }
    return {
        "answered": answered,
        "total": len(CORE_POOL),
        "completed": len(answered),
    }


@router.get("/next-item")
async def get_next_psychometric_item(
    connector: str | None = None,
    user_id: UUID = Depends(get_current_user_id),
):
    """Return the next unanswered psychometric item for this user."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT item_id FROM psychometric_responses WHERE user_id = $1",
            str(user_id),
        )
    answered_ids = {r["item_id"] for r in rows}
    item = get_next_item(answered_ids, connector)
    if not item:
        return None

    return {
        "item_id": item["item_id"],
        "instrument": item["instrument"],
        "text": item["text"],
        "scale": item["scale"],
        "options": item["options"],
        "connector_affinity": item["connector_affinity"],
        "progress": {
            "answered": len(answered_ids),
            "core_total": len(CORE_POOL),
        },
    }


@router.get("/next-items")
async def get_next_psychometric_items(
    connector: str | None = None,
    count: int = 5,
    user_id: UUID = Depends(get_current_user_id),
):
    """Return up to `count` unanswered psychometric items for this user."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT item_id FROM psychometric_responses WHERE user_id = $1",
            str(user_id),
        )
    answered_ids = {r["item_id"] for r in rows}
    items = get_next_items(answered_ids, connector, count=min(count, 10))
    return [
        {
            "item_id": it["item_id"],
            "instrument": it["instrument"],
            "text": it["text"],
            "scale": it["scale"],
            "options": it["options"],
            "connector_affinity": it["connector_affinity"],
            "progress": {
                "answered": len(answered_ids),
                "core_total": len(CORE_POOL),
            },
        }
        for it in items
    ]
