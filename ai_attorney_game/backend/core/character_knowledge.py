from backend.schemas.episode import EpisodeData
from backend.schemas.session import SessionSnapshot


class CharacterKnowledgeManager:
    def build_context(
        self,
        character_id: str,
        episode: EpisodeData,
        session: SessionSnapshot,
    ) -> dict:
        scope = episode.character_knowledge_scope.get(character_id, ["public_evidence", "court_records"])
        ctx: dict = {"character_id": character_id, "scope": scope}

        if "public_evidence" in scope or "inventory" in scope:
            ev_ids = session.revealed_evidence or session.inventory
            ctx["public_evidence"] = [
                e.model_dump()
                for e in episode.evidences
                if e.id in ev_ids
            ]

        if "court_records" in scope:
            ctx["court_records"] = [r.model_dump() for r in session.court_records]

        if "own_statements" in scope:
            ctx["own_statements"] = [
                r.model_dump()
                for r in session.court_records
                if r.speaker == character_id
            ]

        if "scripted_trap" in scope:
            ctx["scripted_trap"] = episode.scripted_trap

        if "allowed_lies" in scope:
            ctx["allowed_lies"] = episode.allowed_lies

        # Never expose absolute truth culprit to non-omniscient roles
        if "absolute_truth" not in scope:
            ctx["forbidden_topics"] = episode.forbidden_claims

        return ctx
