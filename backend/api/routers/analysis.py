import os
import re
import sys
import time
import traceback
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

try:
    from transformers import pipeline
except ImportError:
    pipeline = None


# Ensure project root is in path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.api.uploads import per_user_limit, read_audio
from backend.auth import require_user
from backend.auth.db import User
from backend.privacy.config import get_privacy_settings
from packages.speech_arena.scoring.modes import known_modes

router = APIRouter()

class JobResponse(BaseModel):
    job_id: str
    status: str

# In-memory job store for analysis runs. Results expire after
# retention.job_results_minutes (configs/privacy/privacy.yaml); recordings are never stored.
job_store: dict[str, Any] = {}

PROMPT_ID_RE = re.compile(r"^[a-z0-9-]{1,64}$")
# Modes come from configs/scoring/modes_v2.0.yaml, so a new mode needs no code change here.
ALLOWED_MODES = set(known_modes())
MAX_TRANSCRIPT_CHARS = 5000


def _expire_jobs() -> None:
    ttl = get_privacy_settings().job_results_minutes * 60
    now = time.time()
    for jid in [j for j, d in job_store.items() if now - d.get("created_at", now) > ttl]:
        job_store.pop(jid, None)


def forget_user_jobs(user_id: str) -> None:
    """Drop every result held for a user (called when the account is deleted)."""
    for jid in [j for j, d in job_store.items() if d.get("owner_id") == user_id]:
        job_store.pop(jid, None)

def process_audio_pipeline(
    job_id: str,
    part_bytes: bytes,
    ref_bytes: bytes | None,
    mode: str,
    transcript: str = "",
    prompt_id: str = "",
):
    """
    Executes neural Wav2Vec2 + acoustic feature flaw detection
    and populates the job_store with structured results.
    """
    try:
        if not transcript:
            transcript = "Speech test recording"

        # Check if participant audio data was received
        if not part_bytes:
            raise ValueError("Participant audio file is empty.")

        # Run neural inference
        # Imported here, not at module load, so the API (sign-in, accounts, other pages)
        # still starts when the ML stack or model code is unavailable.
        from ml.inference.predict import SpeechFlawPredictor

        predictor = SpeechFlawPredictor.get_instance()
        ml_result = predictor.predict_audio(
            audio_input=part_bytes,
            transcript=transcript,
            mode=mode
        )

        job_store[job_id] = {
            **job_store.get(job_id, {}),
            "status": "completed",
            "result": {
                "mode": ml_result["mode"],
                # total, buckets, bonuses, bonus_rules, scoring_version, config_hash
                "score": ml_result["score"],
                "metrics": ml_result.get("metrics", {}),
                "flaws": ml_result["flaws"],
                "words": ml_result.get("words", []),
                "duration": ml_result.get("duration", 0.0),
                "contours": ml_result.get("contours", None)
            }
        }
        if prompt_id:
            # Ranked only for opted-in users on a leaderboard passage (see backend/leaderboard).
            from backend.leaderboard.router import submit_result

            owner = job_store[job_id].get("owner_id", "")
            try:
                board = submit_result(owner, prompt_id, float(ml_result["score"]["total"]))
            except Exception:  # noqa: BLE001 - a ranking problem must not discard the analysis
                traceback.print_exc()
                board = {"eligible": True, "submitted": False, "reason": "The leaderboard is unavailable right now."}
            job_store[job_id]["result"]["leaderboard"] = board
    except Exception as e:  # noqa: BLE001 - any pipeline failure becomes a job error, not a crash
        traceback.print_exc()
        print(f"Exception in process_audio_pipeline: {e}")
        
        job_store[job_id] = {
            **job_store.get(job_id, {}),
            "status": "error",
            # Details stay in the server log; the user gets the error type and a hint only.
            "message": f"The analysis failed on the server ({type(e).__name__}). Make sure the backend runs with all ML dependencies installed (`uv run uvicorn backend.api.main:app`)."
        }

@router.post("/analyze", response_model=JobResponse)
async def create_analysis(
    background_tasks: BackgroundTasks,
    reference: UploadFile = File(None),
    participant: UploadFile = File(...),
    transcript: str = Form(""),
    mode: str = Form("sandbox"),
    prompt_id: str = Form("", max_length=64),
    user: User = Depends(require_user),
):
    cfg = get_privacy_settings()
    per_user_limit("analyze", user.id, cfg.analyze_per_hour)
    if mode not in ALLOWED_MODES:
        raise HTTPException(422, "Unknown practice mode.")
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        raise HTTPException(422, f"Keep the transcript under {MAX_TRANSCRIPT_CHARS} characters.")
    if prompt_id and not PROMPT_ID_RE.match(prompt_id):
        raise HTTPException(422, "Unknown reference passage.")

    # Read (bounded and type-checked) before creating the job, so a rejected upload leaves nothing behind.
    part_bytes = await read_audio(participant, "Your recording")
    ref_bytes = await read_audio(reference, "The reference recording") if reference and reference.filename else None

    _expire_jobs()
    job_id = str(uuid.uuid4())
    # owner_id: only the user who started a job can read its result.
    job_store[job_id] = {"status": "processing", "owner_id": user.id, "created_at": time.time()}

    background_tasks.add_task(
        process_audio_pipeline,
        job_id,
        part_bytes,
        ref_bytes,
        mode,
        transcript,
        prompt_id,
    )
    return {"job_id": job_id, "status": "processing"}

@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str, user: User = Depends(require_user)):
    _expire_jobs()
    data = job_store.get(job_id)
    # Another user's job looks exactly like a missing one. Admins get no exception:
    # results describe a person's voice, and running the service doesn't require reading them.
    if data is None or data.get("owner_id") != user.id:
        return {"job_id": job_id, "status": "not_found"}

    if data["status"] == "processing":
        return {"job_id": job_id, "status": "processing"}

    public = {k: v for k, v in data.items() if k not in ("owner_id", "created_at")}
    return {
        "job_id": job_id,
        **public
    }

PRACTICE_SCRIPTS = [
    "The future does not belong to those who wait for certainty. It belongs to those who have the courage to take the first step when the path ahead is still obscured. We must build with purpose, speak with clarity, and lead with empathy.",
    "Over the past three quarters, our operational efficiency improved by twenty-four percent while customer retention reached an all-time high. The key driver was not cutting corners, but streamlining cross-functional alignment and prioritizing high-leverage product initiatives.",
    "Complex systems fail in complex ways. By isolating state, eliminating hidden dependencies, and enforcing deterministic contracts across services, we turn unpredictable failures into observable, self-healing events.",
    "When our deployment pipeline experienced an unexpected outage during peak hours, I immediately convened our incident response squad, established clear communication channels, and rolled back the offending migration within eight minutes.",
    "Global markets stabilized today as central banks signaled a pause in interest rate hikes, pointing to cooling consumer inflation. In technology, renewable infrastructure investments surged past quarterly projections across North America and Europe.",
    "The measure of true innovation is not whether a technology can be built, but whether it serves the genuine welfare of the society that sustains it. Progress without accountability is merely disruption without direction.",
    "The wind howled across the ridge as the fog began to settle over the valley. In the distance, a solitary light flickered through the pine trees, reminding us that no matter how treacherous the climb, warmth was waiting at the summit.",
    "We choose to go to the moon in this decade and do the other things, not because they are easy, but because they are hard, because that goal will serve to organize and measure the best of our energies and skills.",
    "Recent observations from deep-space telescopes have revealed atmospheric signatures on distant exoplanets that defy our previous models. Every discovery reminds us that the universe is far richer and more nuanced than our textbooks suggest.",
    "A great team is not defined by an absence of obstacles, but by the resilience with which they confront them. When everyone shares a common vision and trusts each other completely, even insurmountable challenges become milestones."
]

@router.post("/generate-script")
async def generate_script(user: User = Depends(require_user)):
    per_user_limit("generate", user.id, get_privacy_settings().generate_per_hour)

    try:
        import random
        # First try to pull a rich passage from the RAG corpus if available
        try:
            from backend.rag.retriever import get_retriever
            retriever = get_retriever()
            domains = ["newsroom", "debate", "storytelling"]
            domain = random.choice(domains)
            docs = retriever.in_domain(domain)
            if docs:
                chosen = random.choice(docs)
                content = chosen.get("content", "").strip()
                if content and len(content) > 30:
                    # Take the first ~2-3 sentences (around 50-80 words)
                    sentences = [s.strip() for s in content.split(".") if s.strip()]
                    if len(sentences) >= 2:
                        passage = ". ".join(sentences[:3]) + "."
                        return {"transcript": passage}
        except Exception:
            pass

        # Fallback to curated high-quality speech practice passages
        return {"transcript": random.choice(PRACTICE_SCRIPTS)}
    except Exception as e:  # noqa: BLE001 - generation is best effort; return a message instead
        print(f"Generation error: {e}")
        return {"transcript": "Welcome everyone. I am excited to share some new insights regarding our communication strategy."}

_asr_pipeline = None

@router.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...), user: User = Depends(require_user)):
    global _asr_pipeline
    per_user_limit("transcribe", user.id, get_privacy_settings().transcribe_per_hour)
    audio = await read_audio(file, "Your recording")

    if pipeline is None:
        return {"transcript": "transformers library is not installed."}

    try:
        import warnings
        from transformers import logging as hf_logging
        from ml.inference.predict import decode_audio_to_array

        warnings.filterwarnings("ignore", category=UserWarning)
        warnings.filterwarnings("ignore", category=FutureWarning)
        hf_logging.set_verbosity_error()
        if _asr_pipeline is None:
            _asr_pipeline = pipeline("automatic-speech-recognition", model="openai/whisper-tiny.en", chunk_length_s=30)
            if hasattr(_asr_pipeline, "tokenizer") and _asr_pipeline.tokenizer is not None:
                _asr_pipeline.tokenizer.clean_up_tokenization_spaces = False

        # In-memory audio decoding into 16kHz float32 waveform (bypasses disk temp files and transformers' ffmpeg_read)
        y, sr = decode_audio_to_array(audio, target_sr=16000)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = _asr_pipeline({"raw": y, "sampling_rate": sr})
        return {"transcript": result["text"].strip()}
    except Exception:  # noqa: BLE001 - report a failed transcription cleanly
        traceback.print_exc()
        return {"transcript": "", "error": "Transcription failed on the server."}
