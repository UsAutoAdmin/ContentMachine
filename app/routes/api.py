import json
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.repositories.videos import (
    add_video,
    delete_video,
    find_similar_transcript,
    get_stats,
    get_video,
    import_csv,
    list_videos,
    reset_and_import_csv,
    update_video,
)
from app.services.transcription import list_profile_reels, transcribe_reel

router = APIRouter()


@router.post("/transcribe")
async def transcribe(url: str = Form(...), model_size: str = Form("base")):
    if os.environ.get("VERCEL"):
        raise HTTPException(status_code=503, detail="Transcription requires FFmpeg and runs locally. Use the app on your machine.")
    if not url.strip():
        raise HTTPException(status_code=400, detail="URL is required")
    if "instagram.com" not in url and "instagr.am" not in url:
        raise HTTPException(status_code=400, detail="Please provide a valid Instagram reel URL")
    valid_models = ["tiny", "base", "small", "medium", "large-v2", "large-v3"]
    if model_size not in valid_models:
        model_size = "base"
    try:
        result = transcribe_reel(url.strip(), model_size=model_size)
        return {
            "success": True,
            "transcription": result["transcription"],
            "insights": {
                "view_count": result.get("view_count"),
                "like_count": result.get("like_count"),
                "comment_count": result.get("comment_count"),
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}. Ensure FFmpeg is installed.")


@router.get("/api/videos")
async def api_list_videos(limit: int = 200, offset: int = 0, search: str = ""):
    return {"videos": list_videos(limit=limit, offset=offset, search=search)}


@router.get("/api/videos/{video_id:int}")
async def api_get_video(video_id: int):
    v = get_video(video_id)
    if not v:
        raise HTTPException(404, "Video not found")
    return v


@router.put("/api/videos/{video_id:int}")
async def api_update_video(video_id: int, data: dict):
    if not get_video(video_id):
        raise HTTPException(404, "Video not found")
    update_video(video_id, data)
    return {"ok": True}


@router.post("/api/videos")
async def api_add_video(data: dict):
    return {"id": add_video(data), "ok": True}


@router.delete("/api/videos/{video_id:int}")
async def api_delete_video(video_id: int):
    if not delete_video(video_id):
        raise HTTPException(404, "Video not found")
    return {"ok": True}


@router.get("/api/stats")
async def api_stats():
    return get_stats()


@router.get("/api/bulk-transcribe")
async def bulk_transcribe(profile_url: str, model_size: str = "base"):
    if os.environ.get("VERCEL"):
        raise HTTPException(status_code=503, detail="Bulk transcription requires FFmpeg and runs locally.")
    valid_models = ["tiny", "base", "small", "medium", "large-v2", "large-v3"]
    if model_size not in valid_models:
        model_size = "base"

    async def event_stream():
        def send(data: dict) -> str:
            return f"data: {json.dumps(data)}\n\n"

        yield send({"type": "status", "message": "Fetching reels from profile..."})
        try:
            reels = list_profile_reels(profile_url.strip())
        except ValueError as e:
            yield send({"type": "error", "message": str(e)})
            return
        if not reels:
            yield send({"type": "error", "message": "No reels found on this profile."})
            return
        yield send({"type": "status", "message": f"Found {len(reels)} reels. Starting transcription..."})

        transcribed_count = 0
        for i, reel in enumerate(reels):
            reel_url = reel["url"]
            yield send({"type": "progress", "current": i + 1, "total": len(reels), "message": f"Transcribing reel {i + 1}/{len(reels)}...", "url": reel_url})
            try:
                result = transcribe_reel(reel_url, model_size=model_size)
            except Exception as e:
                yield send({"type": "reel_error", "current": i + 1, "url": reel_url, "message": f"Failed to transcribe: {e}"})
                continue
            transcript = result["transcription"]
            match = find_similar_transcript(transcript)
            if match:
                yield send({
                    "type": "duplicate",
                    "current": i + 1,
                    "url": reel_url,
                    "transcript": transcript[:200],
                    "similarity": round(match["similarity"] * 100, 1),
                    "matched_id": match["video"]["id"],
                    "message": f"Matched existing video #{match['video']['id']} ({round(match['similarity'] * 100, 1)}% similar). Stopping.",
                })
                break
            new_id = add_video({"transcript": transcript, "views": result.get("view_count")})
            transcribed_count += 1
            yield send({"type": "transcribed", "current": i + 1, "total": len(reels), "url": reel_url, "video_id": new_id, "transcript": transcript[:200], "views": result.get("view_count"), "message": f"Saved as video #{new_id}"})

        yield send({"type": "done", "transcribed": transcribed_count, "message": f"Bulk transcription complete. {transcribed_count} new videos added."})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/api/import")
async def api_import_csv(file: UploadFile = File(...), replace: str = Form("false")):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Please upload a CSV file")
    content = await file.read()
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        imported, errors = reset_and_import_csv(tmp_path) if str(replace).lower() in ("true", "1", "yes") else import_csv(tmp_path)
        return {"imported": imported, "errors": errors}
    finally:
        tmp_path.unlink(missing_ok=True)
