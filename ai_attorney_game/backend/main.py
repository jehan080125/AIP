import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ValidationError

from backend.core.court_orchestrator import CourtOrchestrator
from backend.core.state_manager import StateManager
from backend.logging_config import setup_logging, get_logger
from backend.schemas.session import GamePhase
from backend.services.database import GameDatabase
from backend.services.episode_loader import episode_public_view, list_episode_ids, load_episode

setup_logging()
logger = get_logger(__name__)

state_manager = StateManager()
court = CourtOrchestrator(state_manager)
db = GameDatabase()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init()
    yield


app = FastAPI(title="AI Attorney Game API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateSessionRequest(BaseModel):
    episode_id: str = "ep1_tutorial"
    player_role: str = "defense"
    difficulty: str = "easy"


class CollectEvidenceRequest(BaseModel):
    object_id: str
    evidence_id: str


class StartCourtRequest(BaseModel):
    pass


@app.get("/api/episodes")
async def get_episodes():
    ids = list_episode_ids()
    items = []
    for eid in ids:
        ep = load_episode(eid)
        items.append(
            {
                "episode_id": ep.episode_id,
                "title": ep.title,
                "difficulty_available": ep.difficulty_available,
            }
        )
    return {"episodes": items}


@app.get("/api/episodes/{episode_id}")
async def get_episode(episode_id: str):
    try:
        ep = load_episode(episode_id)
    except FileNotFoundError:
        raise HTTPException(404, "Episode not found")
    return episode_public_view(ep)


@app.post("/api/sessions")
async def create_session(body: CreateSessionRequest):
    session_id = await state_manager.create_session(body.episode_id, body.player_role, body.difficulty)
    ep = load_episode(body.episode_id)
    await court.start_episode(session_id, body.episode_id, body.difficulty)
    return {
        "session_id": session_id,
        "episode": episode_public_view(ep),
        "difficulty": body.difficulty,
    }


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    try:
        snap = await state_manager.get_snapshot(session_id)
    except KeyError:
        raise HTTPException(404, "Session not found")
    return snap.model_dump()


@app.post("/api/sessions/{session_id}/collect")
async def collect_evidence(session_id: str, body: CollectEvidenceRequest):
    try:
        meta = await state_manager.get_meta(session_id)
        ep = load_episode(meta.episode_id)
    except KeyError:
        raise HTTPException(404, "Session not found")

    obj = next((o for o in ep.clickable_objects if o.id == body.object_id), None)
    if not obj:
        raise HTTPException(400, f"Unknown object: {body.object_id}")
    if obj.evidence_id != body.evidence_id:
        raise HTTPException(400, "object_id and evidence_id mismatch")

    inv = await state_manager.add_evidence(session_id, body.evidence_id)
    await db.log_event(session_id, (await state_manager.get_meta(session_id)).current_turn, "collect", body.model_dump())
    logger.info("Collected %s via %s in session %s", body.evidence_id, body.object_id, session_id)
    return {"inventory": inv, "evidence_id": body.evidence_id}


@app.post("/api/sessions/{session_id}/start-court")
async def start_court(session_id: str):
    try:
        events = await court.start_court(session_id)
    except KeyError:
        raise HTTPException(404, "Session not found")
    snap = await state_manager.get_snapshot(session_id)
    return {
        "phase": snap.meta.phase,
        "court_records": [r.model_dump() for r in snap.court_records],
        "trial_state": snap.trial_state,
        "events": events,
    }


async def _handle_ws_message(session_id: str, data: dict) -> list[dict[str, Any]]:
    msg_type = data.get("type", "player_input")
    events: list[dict[str, Any]] = []

    if msg_type == "start_episode":
        events = await court.start_episode(
            session_id,
            data.get("episode_id", "ep1_tutorial"),
            data.get("difficulty", "easy"),
        )
    elif msg_type in ("defense_argument", "player_answer"):
        text = data.get("text", "")
        ev_ids = data.get("selected_evidence_ids") or []
        if data.get("evidence_id"):
            ev_ids = list(set(ev_ids + [data["evidence_id"]]))
        ts = await state_manager.get_trial_state(session_id)
        stage_id = data.get("stage_id") or ts.current_stage_id
        if stage_id:
            from backend.schemas.trial import DefenseArgumentPayload

            try:
                payload = DefenseArgumentPayload(
                    session_id=session_id,
                    stage_id=stage_id,
                    text=text,
                    selected_evidence_ids=ev_ids,
                )
            except ValidationError as e:
                first = e.errors()[0] if e.errors() else {}
                field = ".".join(str(part) for part in first.get("loc", []))
                if field == "selected_evidence_ids":
                    return [{"type": "error", "message": "증거는 최대 2개까지 선택할 수 있습니다."}]
                if field == "text":
                    return [{"type": "error", "message": "주장은 100자 이내로 입력해야 합니다."}]
                return [{"type": "error", "message": "입력 형식이 올바르지 않습니다."}]
            events = await court.process_defense_argument(
                payload.session_id,
                payload.stage_id,
                payload.text,
                payload.selected_evidence_ids,
            )
        else:
            events = await court.process_player_answer(session_id, text, ev_ids)
    elif msg_type == "request_hint":
        events = await court.request_hint(session_id)
    elif msg_type == "restart_stage":
        events = await court.restart_stage(session_id, data.get("stage_id", ""))
    elif msg_type == "summon_witness":
        ts = await state_manager.get_trial_state(session_id)
        events = await court.summon_defense_witness(
            session_id, data.get("stage_id") or ts.current_stage_id or ""
        )
    elif msg_type == "player_input":
        text = data.get("text", "")
        events = await court.process_player_input(session_id, raw_text=text)
    elif msg_type == "structured_action":
        from backend.schemas.actions import ParsedAction

        parsed = ParsedAction.model_validate(data.get("parsed", {}))
        events = await court.process_player_input(session_id, parsed=parsed)
    elif msg_type == "legacy_action":
        events = await court.process_player_input(session_id, legacy_payload=data.get("payload", {}))
    else:
        events = [{"type": "error", "message": f"Unknown message type: {msg_type}"}]

    meta = await state_manager.get_meta(session_id)
    for ev in events:
        await db.log_event(session_id, meta.current_turn, ev.get("type", "unknown"), ev)
    return events


async def _websocket_handler(websocket: WebSocket, session_id: Optional[str] = None) -> None:
    await websocket.accept()
    sid = session_id

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            if not sid:
                sid = data.get("session_id")
                try:
                    if sid:
                        await state_manager.get_meta(sid)
                except KeyError:
                    sid = None

            if not sid:
                sid = await state_manager.create_session(
                    data.get("episode_id", "ep1_tutorial"),
                    difficulty=data.get("difficulty", "easy"),
                )
                await websocket.send_json({"type": "session_created", "session_id": sid})

            events = await _handle_ws_message(sid, data)
            for ev in events:
                await websocket.send_json(ev)

            if len(events) == 1 and events[0].get("type") == "actor_lines":
                lines = events[0].get("lines", [])
                if lines:
                    await websocket.send_json(
                        {
                            "status": "success",
                            "speaker": lines[0].get("speaker", "defendant"),
                            "text": lines[0].get("dialogue", ""),
                            "is_breakdown": False,
                            "lines": lines,
                        }
                    )
            elif len(events) == 1 and events[0].get("type") == "breakdown":
                lines = events[0].get("lines", [])
                text = lines[0].get("dialogue", "") if lines else ""
                await websocket.send_json(
                    {
                        "status": "breakdown",
                        "speaker": "defendant",
                        "text": text,
                        "is_breakdown": True,
                        "reason": events[0].get("reason", ""),
                        "lines": lines,
                    }
                )

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected session=%s", sid)
    except Exception as e:
        logger.exception("WebSocket error: %s", e)
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


@app.websocket("/ws/trial")
async def websocket_trial(websocket: WebSocket):
    await _websocket_handler(websocket, None)


@app.websocket("/ws/trial/{session_id}")
async def websocket_trial_with_session(websocket: WebSocket, session_id: str):
    await _websocket_handler(websocket, session_id)
