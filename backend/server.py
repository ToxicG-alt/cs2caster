from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import asyncio
import logging
import tempfile
import uuid
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from datetime import datetime, timezone

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

OUTPUT_DIR = ROOT_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

app = FastAPI()
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# In-memory progress tracker (single worker)
PROGRESS = {}

from cs2.pipeline import run_pipeline, make_source
from cs2.config import get_config


class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StatusCheckCreate(BaseModel):
    client_name: str


@api_router.get("/")
async def root():
    return {"message": "CS2 AI Caster API"}


@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_obj = StatusCheck(**input.model_dump())
    doc = status_obj.model_dump()
    doc['timestamp'] = doc['timestamp'].isoformat()
    await db.status_checks.insert_one(doc)
    return status_obj


# --------------------------------------------------------------------------- #
# CS2 AI Caster endpoints
# --------------------------------------------------------------------------- #
async def _process_match(match_id: str, demo_bytes: Optional[bytes] = None):
    def progress(stage, pct):
        PROGRESS[match_id] = {"stage": stage, "progress": pct}
    demo_path = None
    try:
        PROGRESS[match_id] = {"stage": "starting", "progress": 1}
        if demo_bytes is not None:
            tf = tempfile.NamedTemporaryFile(suffix=".dem", delete=False)
            tf.write(demo_bytes)
            tf.close()
            demo_path = tf.name
        source = make_source(demo_path)
        out_dir = OUTPUT_DIR / match_id
        cfg = get_config()
        result = await run_pipeline(source, str(out_dir), cfg=cfg, progress=progress)
        await db.cs2_matches.update_one(
            {"id": match_id},
            {"$set": {"status": "done", "result": result,
                      "finished_at": datetime.now(timezone.utc).isoformat()}})
        PROGRESS[match_id] = {"stage": "done", "progress": 100}
    except Exception as e:  # noqa
        logger.exception("pipeline failed for %s", match_id)
        await db.cs2_matches.update_one(
            {"id": match_id}, {"$set": {"status": "error", "error": str(e)}})
        PROGRESS[match_id] = {"stage": "error", "progress": 100, "error": str(e)}
    finally:
        if demo_path and os.path.exists(demo_path):
            try:
                os.remove(demo_path)
            except OSError:
                pass


async def _create_match(source_kind: str, filename: str):
    match_id = str(uuid.uuid4())
    doc = {"id": match_id, "status": "processing", "source": source_kind,
           "filename": filename, "created_at": datetime.now(timezone.utc).isoformat()}
    await db.cs2_matches.insert_one(doc)
    asyncio.create_task(_process_match(match_id))
    return match_id


@api_router.post("/cs2/sample")
async def create_sample_match():
    """Process the built-in synthetic sample match (no .dem needed)."""
    match_id = await _create_match("synthetic", "Sample Match (de_nuke)")
    return {"id": match_id, "status": "processing"}


@api_router.post("/cs2/upload")
async def upload_demo(file: UploadFile = File(...)):
    if not file.filename.endswith(".dem"):
        raise HTTPException(400, "Please upload a CS2 .dem file")
    demo_bytes = await file.read()
    match_id = str(uuid.uuid4())
    doc = {"id": match_id, "status": "processing", "source": "demo",
           "filename": file.filename, "created_at": datetime.now(timezone.utc).isoformat()}
    await db.cs2_matches.insert_one(doc)
    asyncio.create_task(_process_match(match_id, demo_bytes))
    return {"id": match_id, "status": "processing"}


@api_router.get("/cs2/matches")
async def list_matches():
    docs = await db.cs2_matches.find({}, {"_id": 0, "result": 0}).sort("created_at", -1).to_list(100)
    return docs


@api_router.get("/cs2/matches/{match_id}")
async def get_match(match_id: str):
    doc = await db.cs2_matches.find_one({"id": match_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Match not found")
    doc["live_progress"] = PROGRESS.get(match_id)
    return doc


@api_router.get("/cs2/matches/{match_id}/audio/{clip}")
async def get_audio(match_id: str, clip: str):
    path = OUTPUT_DIR / match_id / "audio" / clip
    if not path.exists():
        raise HTTPException(404, "Audio not found")
    return FileResponse(str(path), media_type="audio/mpeg")


@api_router.get("/cs2/config")
async def get_default_config():
    return get_config()


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
