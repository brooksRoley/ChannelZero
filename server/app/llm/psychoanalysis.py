from __future__ import annotations

import json
from uuid import UUID
from typing import Dict, Any, Optional

from ..db import get_pool
from .chat import chat_completion

async def generate_psychoanalysis_narrative(user_id: UUID, profile_data: Dict[str, Any]) -> str:
    """
    Generates a subjective, warm, and insightful psychological narrative 
    based on the user's computed psychometric scores and behavioral data.
    """
    pool = get_pool()

    # Runs on the server LLM (OpenRouter free tier) — no user key needed.
    async with pool.acquire() as conn:
        # Spotify behavioral data, if connected, from vibe_vectors
        vibe_row = await conn.fetchrow(
            "SELECT spotify_data FROM vibe_vectors WHERE user_id = $1", 
            user_id
        )
        
    spotify_data = None
    if vibe_row and vibe_row["spotify_data"]:
        try:
            spotify_data = json.loads(vibe_row["spotify_data"])
        except json.JSONDecodeError:
            pass

    return await chat_completion(_build_prompt(profile_data, spotify_data), max_tokens=1024)

def _build_prompt(profile: Dict[str, Any], spotify_data: Optional[Dict[str, Any]]) -> str:
    spotify_context = ""
    if spotify_data:
        artists = ", ".join(spotify_data.get("top_artists", []))
        genres = ", ".join(spotify_data.get("genres", []))
        spotify_context = f"\n- Behavioral Audio Preferences (Spotify): Top Genres include {genres}. This often correlates with openness and extraversion levels."
        
    return f"""
You are an expert, warm, and highly insightful relationship psychologist.
Based on the following psychometric assessment data, write a personalized 3-paragraph 
psychoanalysis that helps the user understand their relationship patterns. 
Do not use cold clinical jargon. Be empowering and accurate to the data.

DATA:
- Big Five (IPIP-NEO-50): {json.dumps(profile.get('ipip_neo_scores'))}
- Attachment Style (ECR-R): {json.dumps(profile.get('ecr_r_scores'))}
- Love Language: {profile.get('love_language')}
- Values Cluster: {profile.get('values_cluster')}
- Sociosexual Orientation: {profile.get('sociosexual_orientation')}{spotify_context}

Focus mainly on how their attachment style and Big Five traits interact in dating. Cross-reference their behavioral data (e.g. Spotify) to look for potential public/private self discrepancies if any exist. Keep the tone warm, insightful, and constructive. Return only the narrative content.
"""
