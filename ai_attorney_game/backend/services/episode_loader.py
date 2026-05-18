import json
from pathlib import Path

from backend.config import EPISODES_DIR
from backend.schemas.episode import EpisodeData
from backend.logging_config import get_logger

logger = get_logger(__name__)


def list_episode_ids() -> list[str]:
    if not EPISODES_DIR.exists():
        return []
    return sorted(p.stem for p in EPISODES_DIR.glob("*.json"))


def load_episode(episode_id: str) -> EpisodeData:
    path = EPISODES_DIR / f"{episode_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Episode not found: {episode_id}")
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    episode = EpisodeData.model_validate(raw)
    logger.info("Loaded episode %s", episode_id)
    return episode


def episode_public_view(episode: EpisodeData) -> dict:
    return {
        "episode_id": episode.episode_id,
        "title": episode.title,
        "difficulty_available": episode.difficulty_available,
        "clickable_objects": [o.model_dump() for o in episode.clickable_objects],
        "evidences": [
            {
                "id": e.id,
                "name": e.name,
                "description": e.description,
                "fact": e.fact,
                "details": e.details,
                "tags": e.tags,
            }
            for e in episode.evidences
        ],
        "trial_rounds_count": len(episode.trial_rounds),
        "trials": [t.model_dump() for t in episode.trials],
        "characters": {k: v.model_dump() for k, v in episode.characters.items()},
        "character_files": [cf.model_dump() for cf in episode.character_files]
        or [
            {
                "character_id": c.id,
                "name": c.name,
                "role": c.role,
                "description": c.description,
                "relation_to_defendant": c.relation_to_defendant,
                "known_statements": c.known_statements,
                "credibility_state": c.credibility_state,
                "portrait": c.portrait or c.portrait_idle,
                "expression_state": c.expression_state,
            }
            for c in episode.characters.values()
        ],
    }
