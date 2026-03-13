"""
ContentMachine - Instagram Reel Transcription Tool

Internal tool to paste an Instagram reel URL and get a transcription.
"""

import json
import os
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="ContentMachine", description="Transcribe Instagram Reels")

# Lazy imports for Vercel: heavy deps (faster-whisper, yt-dlp) loaded only when needed
# so the app can start and serve Teleprompter/Performance pages

# Serve static files if we add any
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the main transcription form."""
    return get_index_html()


@app.get("/teleprompter", response_class=HTMLResponse)
async def teleprompter():
    """Serve the teleprompter page."""
    return get_teleprompter_html()


@app.get("/performance", response_class=HTMLResponse)
async def performance():
    """Serve the performance database page."""
    return get_performance_html()


@app.post("/transcribe")
async def transcribe(url: str = Form(...), model_size: str = Form("base")):
    """
    Transcribe an Instagram reel from its URL.
    Returns the transcription text.
    """
    if os.environ.get("VERCEL"):
        raise HTTPException(
            status_code=503,
            detail="Transcription requires FFmpeg and runs locally. Use the app on your machine.",
        )
    from transcribe import transcribe_reel

    if not url.strip():
        raise HTTPException(status_code=400, detail="URL is required")

    # Basic URL validation
    if "instagram.com" not in url and "instagr.am" not in url:
        raise HTTPException(
            status_code=400,
            detail="Please provide a valid Instagram reel URL (e.g. instagram.com/reel/...)",
        )

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
        raise HTTPException(
            status_code=500,
            detail=f"Transcription failed: {str(e)}. Ensure FFmpeg is installed.",
        )


# Performance database API
@app.get("/api/videos")
async def api_list_videos(limit: int = 200, offset: int = 0, search: str = ""):
    from database import list_videos
    return {"videos": list_videos(limit=limit, offset=offset, search=search)}


@app.get("/api/videos/{video_id:int}")
async def api_get_video(video_id: int):
    from database import get_video
    v = get_video(video_id)
    if not v:
        raise HTTPException(404, "Video not found")
    return v


@app.put("/api/videos/{video_id:int}")
async def api_update_video(video_id: int, data: dict):
    from database import get_video, update_video
    if not get_video(video_id):
        raise HTTPException(404, "Video not found")
    update_video(video_id, data)
    return {"ok": True}


@app.post("/api/videos")
async def api_add_video(data: dict):
    from database import add_video
    vid = add_video(data)
    return {"id": vid, "ok": True}


@app.delete("/api/videos/{video_id:int}")
async def api_delete_video(video_id: int):
    from database import delete_video
    if not delete_video(video_id):
        raise HTTPException(404, "Video not found")
    return {"ok": True}


@app.get("/api/stats")
async def api_stats():
    from database import get_stats
    return get_stats()


@app.get("/bulk", response_class=HTMLResponse)
async def bulk_page():
    """Serve the bulk transcribe page."""
    return get_bulk_html()


@app.get("/api/bulk-transcribe")
async def bulk_transcribe(
    profile_url: str,
    model_size: str = "base",
):
    """
    SSE endpoint: scrapes profile reels, transcribes each one, saves to DB,
    and stops when a transcript matches an existing one in the performance DB.
    """
    if os.environ.get("VERCEL"):
        raise HTTPException(
            status_code=503,
            detail="Bulk transcription requires FFmpeg and runs locally.",
        )

    from transcribe import list_profile_reels, transcribe_reel
    from database import add_video, find_similar_transcript

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

        yield send({
            "type": "status",
            "message": f"Found {len(reels)} reels. Starting transcription...",
        })

        transcribed_count = 0
        for i, reel in enumerate(reels):
            reel_url = reel["url"]
            yield send({
                "type": "progress",
                "current": i + 1,
                "total": len(reels),
                "message": f"Transcribing reel {i + 1}/{len(reels)}...",
                "url": reel_url,
            })

            try:
                result = transcribe_reel(reel_url, model_size=model_size)
            except Exception as e:
                yield send({
                    "type": "reel_error",
                    "current": i + 1,
                    "url": reel_url,
                    "message": f"Failed to transcribe: {e}",
                })
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
                    "message": (
                        f"Matched existing video #{match['video']['id']} "
                        f"({round(match['similarity'] * 100, 1)}% similar). Stopping."
                    ),
                })
                break

            video_data = {
                "transcript": transcript,
                "views": result.get("view_count"),
            }
            new_id = add_video(video_data)
            transcribed_count += 1

            yield send({
                "type": "transcribed",
                "current": i + 1,
                "total": len(reels),
                "url": reel_url,
                "video_id": new_id,
                "transcript": transcript[:200],
                "views": result.get("view_count"),
                "message": f"Saved as video #{new_id}",
            })

        yield send({
            "type": "done",
            "transcribed": transcribed_count,
            "message": f"Bulk transcription complete. {transcribed_count} new videos added.",
        })

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/import")
async def api_import_csv(file: UploadFile = File(...), replace: str = Form("false")):
    from database import import_csv, reset_and_import_csv
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Please upload a CSV file")
    content = await file.read()
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        if str(replace).lower() in ("true", "1", "yes"):
            imported, errors = reset_and_import_csv(tmp_path)
        else:
            imported, errors = import_csv(tmp_path)
        return {"imported": imported, "errors": errors}
    finally:
        tmp_path.unlink(missing_ok=True)


def get_index_html() -> str:
    """Return the main UI HTML."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ContentMachine - Reel Insights & Transcription</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Outfit:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #0d0d0f;
            --surface: #16161a;
            --border: #2a2a2e;
            --text: #e4e4e7;
            --text-muted: #71717a;
            --accent: #a78bfa;
            --accent-hover: #c4b5fd;
            --success: #34d399;
            --error: #f87171;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Outfit', sans-serif;
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 2rem;
        }
        .container {
            width: 100%;
            max-width: 560px;
        }
        h1 {
            font-size: 1.75rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
            background: linear-gradient(135deg, var(--accent), #c084fc);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .subtitle {
            color: var(--text-muted);
            font-size: 0.95rem;
            margin-bottom: 2rem;
        }
        form {
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }
        label {
            font-size: 0.875rem;
            font-weight: 500;
            color: var(--text-muted);
        }
        input[type="url"] {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.9rem;
            padding: 0.875rem 1rem;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 10px;
            color: var(--text);
            transition: border-color 0.2s;
        }
        input[type="url"]:focus {
            outline: none;
            border-color: var(--accent);
        }
        input[type="url"]::placeholder {
            color: var(--text-muted);
            opacity: 0.7;
        }
        .row {
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }
        select {
            font-family: 'Outfit', sans-serif;
            padding: 0.5rem 0.75rem;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            color: var(--text);
            font-size: 0.875rem;
        }
        button {
            font-family: 'Outfit', sans-serif;
            font-weight: 600;
            padding: 0.875rem 1.5rem;
            background: linear-gradient(135deg, var(--accent), #8b5cf6);
            border: none;
            border-radius: 10px;
            color: white;
            cursor: pointer;
            transition: transform 0.15s, box-shadow 0.15s;
        }
        button:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 20px rgba(167, 139, 250, 0.35);
        }
        button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }
        .result {
            margin-top: 2rem;
            padding: 1.25rem;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.9rem;
            line-height: 1.6;
            white-space: pre-wrap;
            word-break: break-word;
        }
        .result.success { border-color: rgba(52, 211, 153, 0.4); }
        .result.error { border-color: rgba(248, 113, 113, 0.4); color: var(--error); }
        .insights {
            margin-top: 1.5rem;
            display: flex;
            gap: 1.5rem;
            flex-wrap: wrap;
        }
        .insight {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.5rem 1rem;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            font-size: 0.9rem;
        }
        .insight span { color: var(--text-muted); }
        .insight strong { color: var(--accent); }
        .status {
            margin-top: 1rem;
            font-size: 0.875rem;
            color: var(--text-muted);
        }
        .add-tracker {
            margin-top: 1.5rem;
            padding: 1.25rem;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            display: none;
        }
        .add-tracker.show { display: block; }
        .add-tracker h3 {
            font-size: 0.9rem;
            font-weight: 600;
            margin-bottom: 1rem;
            color: var(--text-muted);
        }
        .tracker-fields {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 0.75rem;
            margin-bottom: 1rem;
        }
        .tracker-fields label {
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-bottom: 0.2rem;
            display: block;
        }
        .tracker-fields input {
            width: 100%;
            padding: 0.5rem 0.75rem;
            background: var(--bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            color: var(--text);
            font-size: 0.85rem;
            font-family: 'JetBrains Mono', monospace;
        }
        .tracker-fields input:focus { outline: none; border-color: var(--accent); }
        .tracker-btn {
            font-family: 'Outfit', sans-serif;
            font-weight: 600;
            padding: 0.6rem 1.25rem;
            background: linear-gradient(135deg, #34d399, #10b981);
            border: none;
            border-radius: 8px;
            color: white;
            cursor: pointer;
            font-size: 0.85rem;
            transition: transform 0.15s, box-shadow 0.15s;
        }
        .tracker-btn:hover { transform: translateY(-1px); box-shadow: 0 4px 16px rgba(52,211,153,0.3); }
        .tracker-msg {
            margin-top: 0.5rem;
            font-size: 0.8rem;
            color: var(--success);
        }
        .nav {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            display: flex;
            gap: 0.5rem;
            padding: 1rem 1.5rem;
            background: var(--surface);
            border-bottom: 1px solid var(--border);
            z-index: 10;
        }
        .nav a {
            color: var(--text-muted);
            text-decoration: none;
            padding: 0.5rem 1rem;
            border-radius: 8px;
            font-weight: 500;
            transition: color 0.2s, background 0.2s;
        }
        .nav a:hover { color: var(--text); background: rgba(167,139,250,0.1); }
        .nav a.active { color: var(--accent); background: rgba(167,139,250,0.15); }
    </style>
</head>
<body>
    <nav class="nav">
        <a href="/" class="active">Transcribe</a>
        <a href="/teleprompter" class="">Teleprompter</a>
        <a href="/performance" class="">Performance</a>
        <a href="/bulk" class="">Bulk Transcribe</a>
    </nav>
    <div class="container" style="margin-top: 4rem;">
        <h1>ContentMachine</h1>
        <p class="subtitle">Paste an Instagram reel link to transcribe and view insights</p>
        <form id="form" action="/transcribe" method="post">
            <label for="url">Instagram Reel URL</label>
            <input type="url" id="url" name="url" placeholder="https://www.instagram.com/reel/..." required>
            <div class="row">
                <label for="model">Model:</label>
                <select id="model" name="model_size">
                    <option value="tiny">Tiny (fastest)</option>
                    <option value="base" selected>Base</option>
                    <option value="small">Small</option>
                    <option value="medium">Medium</option>
                    <option value="large-v2">Large v2</option>
                    <option value="large-v3">Large v3</option>
                </select>
            </div>
            <button type="submit" id="submit">Transcribe</button>
        </form>
        <div id="insights"></div>
        <div id="result"></div>
        <div id="status" class="status"></div>
        <div class="add-tracker" id="tracker">
            <h3>Add to Performance Tracker</h3>
            <div class="tracker-fields">
                <div><label>Views</label><input type="number" id="tViews" placeholder="e.g. 5000"></div>
                <div><label>Skip Rate %</label><input type="number" step="0.01" id="tSkip" placeholder="e.g. 32.5"></div>
                <div><label>Like Rate %</label><input type="number" step="0.01" id="tLike" placeholder="e.g. 3.5"></div>
                <div><label>Retention %</label><input type="number" step="0.01" id="tRetention" placeholder="e.g. 35"></div>
            </div>
            <button class="tracker-btn" id="trackBtn">Save to Tracker</button>
            <div class="tracker-msg" id="trackerMsg"></div>
        </div>
    </div>
    <script>
        const form = document.getElementById('form');
        const resultEl = document.getElementById('result');
        const insightsEl = document.getElementById('insights');
        const statusEl = document.getElementById('status');
        const submitBtn = document.getElementById('submit');
        const tracker = document.getElementById('tracker');
        const trackBtn = document.getElementById('trackBtn');
        const trackerMsg = document.getElementById('trackerMsg');
        let lastTranscription = '';

        function formatCount(v) {
            if (v == null) return '—';
            if (v >= 1e6) return (v/1e6).toFixed(1) + 'M';
            if (v >= 1e3) return (v/1e3).toFixed(1) + 'K';
            return String(v);
        }

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const url = document.getElementById('url').value;
            const modelSize = document.getElementById('model').value;
            resultEl.innerHTML = '';
            resultEl.className = '';
            insightsEl.innerHTML = '';
            statusEl.textContent = 'Downloading and transcribing...';
            submitBtn.disabled = true;

            try {
                const formData = new FormData();
                formData.append('url', url);
                formData.append('model_size', modelSize);
                const res = await fetch('/transcribe', {
                    method: 'POST',
                    body: formData
                });
                const data = await res.json();
                if (res.ok && data.success) {
                    const i = data.insights || {};
                    insightsEl.innerHTML = `
                        <div class="insights">
                            <div class="insight"><span>Views</span><strong>${formatCount(i.view_count)}</strong></div>
                            <div class="insight"><span>Likes</span><strong>${formatCount(i.like_count)}</strong></div>
                            <div class="insight"><span>Comments</span><strong>${formatCount(i.comment_count)}</strong></div>
                        </div>
                    `;
                    resultEl.textContent = data.transcription;
                    resultEl.className = 'result success';
                    statusEl.textContent = 'Done.';
                    lastTranscription = data.transcription;
                    tracker.classList.add('show');
                    trackerMsg.textContent = '';
                    document.getElementById('tViews').value = '';
                    document.getElementById('tSkip').value = '';
                    document.getElementById('tLike').value = '';
                    document.getElementById('tRetention').value = '';
                } else {
                    resultEl.textContent = data.detail || 'Transcription failed';
                    resultEl.className = 'result error';
                    statusEl.textContent = '';
                }
            } catch (err) {
                resultEl.textContent = err.message || 'Network error';
                resultEl.className = 'result error';
                statusEl.textContent = '';
            } finally {
                submitBtn.disabled = false;
            }
        });

        trackBtn.addEventListener('click', async () => {
            if (!lastTranscription) return;
            trackBtn.disabled = true;
            trackerMsg.textContent = 'Saving...';
            try {
                const payload = { transcript: lastTranscription };
                const v = document.getElementById('tViews').value;
                const s = document.getElementById('tSkip').value;
                const l = document.getElementById('tLike').value;
                const r = document.getElementById('tRetention').value;
                if (v) payload.views = parseInt(v);
                if (s) payload.skip_rate = parseFloat(s);
                if (l) payload.like_rate = parseFloat(l);
                if (r) payload.retention_pct = parseFloat(r);
                const res = await fetch('/api/videos', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (data.ok) {
                    trackerMsg.textContent = 'Saved to Performance Tracker (ID ' + data.id + ')';
                    trackerMsg.style.color = 'var(--success, #34d399)';
                } else {
                    trackerMsg.textContent = 'Failed to save';
                    trackerMsg.style.color = 'var(--error, #f87171)';
                }
            } catch (err) {
                trackerMsg.textContent = 'Error: ' + err.message;
                trackerMsg.style.color = 'var(--error, #f87171)';
            } finally {
                trackBtn.disabled = false;
            }
        });
    </script>
</body>
</html>"""


def get_nav_html(active: str) -> str:
    """Navigation links for ContentMachine."""
    transcribe_cls = 'active' if active == 'transcribe' else ''
    teleprompter_cls = 'active' if active == 'teleprompter' else ''
    bulk_cls = 'active' if active == 'bulk' else ''
    return f'''
    <nav class="nav">
        <a href="/" class="{transcribe_cls}">Transcribe</a>
        <a href="/teleprompter" class="{teleprompter_cls}">Teleprompter</a>
        <a href="/performance">Performance</a>
        <a href="/bulk" class="{bulk_cls}">Bulk Transcribe</a>
    </nav>'''


def get_teleprompter_html() -> str:
    """Return the teleprompter page HTML."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ContentMachine - Teleprompter</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #0d0d0f;
            --surface: #16161a;
            --border: #2a2a2e;
            --text: #e4e4e7;
            --text-muted: #71717a;
            --accent: #a78bfa;
            --accent-hover: #c4b5fd;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Outfit', sans-serif;
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        .nav {
            display: flex;
            gap: 0.5rem;
            padding: 1rem 1.5rem;
            background: var(--surface);
            border-bottom: 1px solid var(--border);
        }
        .nav a {
            color: var(--text-muted);
            text-decoration: none;
            padding: 0.5rem 1rem;
            border-radius: 8px;
            font-weight: 500;
            transition: color 0.2s, background 0.2s;
        }
        .nav a:hover { color: var(--text); background: rgba(167,139,250,0.1); }
        .nav a.active { color: var(--accent); background: rgba(167,139,250,0.15); }
        .teleprompter-layout {
            display: flex;
            flex: 1;
            min-height: 0;
        }
        .editor-panel {
            width: 320px;
            flex-shrink: 0;
            padding: 1.5rem;
            border-right: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            gap: 1.25rem;
        }
        .editor-panel h2 {
            font-size: 1.1rem;
            font-weight: 600;
            color: var(--text-muted);
        }
        .editor-panel textarea {
            flex: 1;
            min-height: 120px;
            padding: 1rem;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 10px;
            color: var(--text);
            font-family: inherit;
            font-size: 0.95rem;
            line-height: 1.5;
            resize: vertical;
        }
        .editor-panel textarea:focus {
            outline: none;
            border-color: var(--accent);
        }
        .control-row {
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }
        .control-row label {
            font-size: 0.8rem;
            font-weight: 500;
            color: var(--text-muted);
        }
        .control-row input[type="range"] {
            width: 100%;
            height: 6px;
            -webkit-appearance: none;
            background: var(--border);
            border-radius: 3px;
        }
        .control-row input[type="range"]::-webkit-slider-thumb {
            -webkit-appearance: none;
            width: 18px;
            height: 18px;
            background: var(--accent);
            border-radius: 50%;
            cursor: pointer;
            box-shadow: 0 2px 8px rgba(167,139,250,0.4);
        }
        .control-value {
            font-size: 0.8rem;
            color: var(--accent);
            font-weight: 600;
        }
        .play-btn {
            padding: 0.875rem 1.5rem;
            font-family: inherit;
            font-weight: 600;
            font-size: 1rem;
            background: linear-gradient(135deg, var(--accent), #8b5cf6);
            border: none;
            border-radius: 10px;
            color: white;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
            transition: transform 0.15s, box-shadow 0.15s;
        }
        .play-btn:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 20px rgba(167,139,250,0.35);
        }
        .play-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
        }
        .prompter-view {
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: flex-start;
            padding: 3rem 2rem;
            overflow: hidden;
            position: relative;
        }
        .prompter-scroll {
            width: 100%;
            max-width: 720px;
            text-align: center;
            transform: translateY(0);
            transition: none;
            white-space: pre-wrap;
            word-break: break-word;
            line-height: 1.6;
        }
        .prompter-scroll.scrolling {
            transition: transform 0.05s linear;
        }
    </style>
</head>
<body>
    <nav class="nav">
        <a href="/" class="">Transcribe</a>
        <a href="/teleprompter" class="active">Teleprompter</a>
        <a href="/performance" class="">Performance</a>
        <a href="/bulk" class="">Bulk Transcribe</a>
    </nav>
    <div class="teleprompter-layout">
        <aside class="editor-panel">
            <h2>Script</h2>
            <textarea id="script" placeholder="Paste your script here..."></textarea>
            <div class="control-row">
                <label>Speed</label>
                <input type="range" id="speed" min="0.5" max="4" step="0.1" value="1.5">
                <span class="control-value" id="speedVal">1.5x</span>
            </div>
            <div class="control-row">
                <label>Text size</label>
                <input type="range" id="size" min="1" max="5" step="0.5" value="2.5">
                <span class="control-value" id="sizeVal">2.5</span>
            </div>
            <div style="display:flex;gap:0.5rem;">
                <button class="play-btn" id="playBtn" style="flex:1;">
                    <span id="playIcon">▶</span>
                    <span id="playLabel">Play</span>
                </button>
                <button class="play-btn" id="resetBtn" style="flex:0;padding:0.875rem 1rem;" title="Restart from top">↺</button>
            </div>
        </aside>
        <main class="prompter-view">
            <div class="prompter-scroll" id="prompterText">Paste a script and press Play</div>
        </main>
    </div>
    <script>
        const scriptEl = document.getElementById('script');
        const prompterEl = document.getElementById('prompterText');
        const playBtn = document.getElementById('playBtn');
        const playIcon = document.getElementById('playIcon');
        const playLabel = document.getElementById('playLabel');
        const speedSlider = document.getElementById('speed');
        const speedVal = document.getElementById('speedVal');
        const sizeSlider = document.getElementById('size');
        const sizeVal = document.getElementById('sizeVal');
        const resetBtn = document.getElementById('resetBtn');

        let playing = false;
        let scrollPos = 0;
        let rafId = null;
        let lastTime = 0;

        const sizePx = (v) => Math.round(20 + (v - 1) * 12) + 'px';

        function syncDisplay() {
            prompterEl.textContent = scriptEl.value || 'Paste a script and press Play';
            prompterEl.style.fontSize = sizePx(parseFloat(sizeSlider.value));
        }

        function updateScroll(t) {
            if (!playing) return;
            const dt = t - lastTime;
            lastTime = t;
            const speed = parseFloat(speedSlider.value) * 80;
            scrollPos += dt * 0.001 * speed;
            const view = prompterEl.parentElement;
            const maxScroll = Math.max(0, prompterEl.offsetHeight - view.clientHeight + 80);
            if (scrollPos >= maxScroll) {
                scrollPos = maxScroll;
                playing = false;
                playIcon.textContent = '▶';
                playLabel.textContent = 'Play';
            }
            prompterEl.style.transform = `translateY(-${scrollPos}px)`;
            rafId = requestAnimationFrame(updateScroll);
        }

        playBtn.addEventListener('click', () => {
            if (playing) {
                playing = false;
                if (rafId) cancelAnimationFrame(rafId);
                playIcon.textContent = '▶';
                playLabel.textContent = 'Play';
            } else {
                syncDisplay();
                if (!scriptEl.value.trim()) return;
                prompterEl.classList.add('scrolling');
                playing = true;
                playIcon.textContent = '⏸';
                playLabel.textContent = 'Pause';
                lastTime = performance.now();
                rafId = requestAnimationFrame(updateScroll);
            }
        });

        scriptEl.addEventListener('input', () => {
            if (!playing) {
                syncDisplay();
                scrollPos = 0;
                prompterEl.style.transform = 'translateY(0)';
            }
        });

        resetBtn.addEventListener('click', () => {
            scrollPos = 0;
            prompterEl.style.transform = 'translateY(0)';
            if (playing) {
                playing = false;
                if (rafId) cancelAnimationFrame(rafId);
                playIcon.textContent = '▶';
                playLabel.textContent = 'Play';
            }
        });

        speedSlider.addEventListener('input', () => {
            speedVal.textContent = parseFloat(speedSlider.value).toFixed(1) + 'x';
        });

        sizeSlider.addEventListener('input', () => {
            const v = parseFloat(sizeSlider.value);
            sizeVal.textContent = v.toFixed(1);
            prompterEl.style.fontSize = sizePx(v);
        });

        document.addEventListener('keydown', (e) => {
            if (e.code === 'Space' && e.target.tagName !== 'TEXTAREA') {
                e.preventDefault();
                playBtn.click();
            }
        });

        syncDisplay();
    </script>
</body>
</html>"""


def get_bulk_html() -> str:
    """Return the bulk transcribe page HTML."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ContentMachine - Bulk Transcribe</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Outfit:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #0d0d0f;
            --surface: #16161a;
            --border: #2a2a2e;
            --text: #e4e4e7;
            --text-muted: #71717a;
            --accent: #a78bfa;
            --accent-hover: #c4b5fd;
            --success: #34d399;
            --error: #f87171;
            --warning: #fbbf24;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Outfit', sans-serif;
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
        }
        .nav {
            position: sticky;
            top: 0;
            display: flex;
            gap: 0.5rem;
            padding: 1rem 1.5rem;
            background: var(--surface);
            border-bottom: 1px solid var(--border);
            z-index: 10;
        }
        .nav a {
            color: var(--text-muted);
            text-decoration: none;
            padding: 0.5rem 1rem;
            border-radius: 8px;
            font-weight: 500;
            transition: color 0.2s, background 0.2s;
        }
        .nav a:hover { color: var(--text); background: rgba(167,139,250,0.1); }
        .nav a.active { color: var(--accent); background: rgba(167,139,250,0.15); }

        .page {
            max-width: 720px;
            margin: 0 auto;
            padding: 2.5rem 1.5rem;
        }
        h1 {
            font-size: 1.75rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
            background: linear-gradient(135deg, var(--accent), #c084fc);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .subtitle {
            color: var(--text-muted);
            font-size: 0.95rem;
            margin-bottom: 2rem;
            line-height: 1.5;
        }
        .form-group {
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
            margin-bottom: 1.5rem;
        }
        label {
            font-size: 0.875rem;
            font-weight: 500;
            color: var(--text-muted);
        }
        input[type="url"] {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.9rem;
            padding: 0.875rem 1rem;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 10px;
            color: var(--text);
            transition: border-color 0.2s;
        }
        input[type="url"]:focus { outline: none; border-color: var(--accent); }
        input[type="url"]::placeholder { color: var(--text-muted); opacity: 0.7; }
        .row { display: flex; align-items: center; gap: 0.75rem; }
        select {
            font-family: 'Outfit', sans-serif;
            padding: 0.5rem 0.75rem;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            color: var(--text);
            font-size: 0.875rem;
        }
        button {
            font-family: 'Outfit', sans-serif;
            font-weight: 600;
            padding: 0.875rem 1.5rem;
            background: linear-gradient(135deg, var(--accent), #8b5cf6);
            border: none;
            border-radius: 10px;
            color: white;
            cursor: pointer;
            transition: transform 0.15s, box-shadow 0.15s;
        }
        button:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 20px rgba(167, 139, 250, 0.35);
        }
        button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
        }
        .stop-btn {
            background: linear-gradient(135deg, var(--error), #dc2626);
            margin-left: 0.75rem;
        }
        .stop-btn:hover { box-shadow: 0 4px 20px rgba(248, 113, 113, 0.35); }

        .progress-area {
            margin-top: 2rem;
            display: none;
        }
        .progress-area.active { display: block; }
        .progress-bar-container {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 10px;
            overflow: hidden;
            height: 8px;
            margin-bottom: 1rem;
        }
        .progress-bar {
            height: 100%;
            background: linear-gradient(90deg, var(--accent), #8b5cf6);
            transition: width 0.3s ease;
            width: 0%;
        }
        .progress-status {
            font-size: 0.9rem;
            color: var(--text-muted);
            margin-bottom: 1.5rem;
        }

        .log-container {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            max-height: 500px;
            overflow-y: auto;
        }
        .log-entry {
            padding: 0.85rem 1.1rem;
            border-bottom: 1px solid var(--border);
            font-size: 0.85rem;
            line-height: 1.5;
            display: flex;
            gap: 0.75rem;
            align-items: flex-start;
        }
        .log-entry:last-child { border-bottom: none; }
        .log-icon {
            flex-shrink: 0;
            width: 22px;
            height: 22px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.7rem;
            margin-top: 1px;
        }
        .log-icon.success { background: rgba(52,211,153,0.15); color: var(--success); }
        .log-icon.error { background: rgba(248,113,113,0.15); color: var(--error); }
        .log-icon.warning { background: rgba(251,191,36,0.15); color: var(--warning); }
        .log-icon.info { background: rgba(167,139,250,0.15); color: var(--accent); }
        .log-content { flex: 1; min-width: 0; }
        .log-message { color: var(--text); }
        .log-detail {
            margin-top: 0.35rem;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.78rem;
            color: var(--text-muted);
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .log-detail.wrap {
            white-space: normal;
            word-break: break-word;
        }

        .summary-card {
            margin-top: 1.5rem;
            padding: 1.25rem;
            background: var(--surface);
            border: 1px solid rgba(52,211,153,0.3);
            border-radius: 12px;
            display: none;
        }
        .summary-card.active { display: block; }
        .summary-card h3 {
            font-size: 1rem;
            font-weight: 600;
            color: var(--success);
            margin-bottom: 0.5rem;
        }
        .summary-card p {
            font-size: 0.9rem;
            color: var(--text-muted);
        }
    </style>
</head>
<body>
    <nav class="nav">
        <a href="/">Transcribe</a>
        <a href="/teleprompter">Teleprompter</a>
        <a href="/performance">Performance</a>
        <a href="/bulk" class="active">Bulk Transcribe</a>
    </nav>

    <div class="page">
        <h1>Bulk Transcribe</h1>
        <p class="subtitle">
            Paste an Instagram profile link to transcribe all reels automatically.
            Stops when it finds a reel that already exists in your Performance Tracker.
        </p>

        <div class="form-group">
            <label for="profileUrl">Instagram Profile URL</label>
            <input type="url" id="profileUrl" placeholder="https://www.instagram.com/username/" required>
            <div class="row">
                <label for="bulkModel">Model:</label>
                <select id="bulkModel">
                    <option value="tiny">Tiny (fastest)</option>
                    <option value="base" selected>Base</option>
                    <option value="small">Small</option>
                    <option value="medium">Medium</option>
                    <option value="large-v2">Large v2</option>
                    <option value="large-v3">Large v3</option>
                </select>
            </div>
            <div class="row">
                <button id="startBtn">Start Bulk Transcribe</button>
                <button id="stopBtn" class="stop-btn" style="display:none;">Stop</button>
            </div>
        </div>

        <div class="progress-area" id="progressArea">
            <div class="progress-bar-container">
                <div class="progress-bar" id="progressBar"></div>
            </div>
            <div class="progress-status" id="progressStatus">Starting...</div>
            <div class="log-container" id="logContainer"></div>
        </div>

        <div class="summary-card" id="summaryCard">
            <h3 id="summaryTitle">Done</h3>
            <p id="summaryText"></p>
        </div>
    </div>

    <script>
        const profileUrl = document.getElementById('profileUrl');
        const bulkModel = document.getElementById('bulkModel');
        const startBtn = document.getElementById('startBtn');
        const stopBtn = document.getElementById('stopBtn');
        const progressArea = document.getElementById('progressArea');
        const progressBar = document.getElementById('progressBar');
        const progressStatus = document.getElementById('progressStatus');
        const logContainer = document.getElementById('logContainer');
        const summaryCard = document.getElementById('summaryCard');
        const summaryTitle = document.getElementById('summaryTitle');
        const summaryText = document.getElementById('summaryText');

        let eventSource = null;

        function addLog(icon, iconClass, message, detail) {
            const entry = document.createElement('div');
            entry.className = 'log-entry';
            entry.innerHTML = `
                <div class="log-icon ${iconClass}">${icon}</div>
                <div class="log-content">
                    <div class="log-message">${esc(message)}</div>
                    ${detail ? '<div class="log-detail">' + esc(detail) + '</div>' : ''}
                </div>
            `;
            logContainer.prepend(entry);
        }

        function esc(s) {
            const d = document.createElement('div');
            d.textContent = s || '';
            return d.innerHTML;
        }

        function stopStream() {
            if (eventSource) {
                eventSource.close();
                eventSource = null;
            }
            startBtn.disabled = false;
            stopBtn.style.display = 'none';
        }

        startBtn.addEventListener('click', () => {
            const url = profileUrl.value.trim();
            if (!url) { profileUrl.focus(); return; }

            startBtn.disabled = true;
            stopBtn.style.display = '';
            progressArea.classList.add('active');
            summaryCard.classList.remove('active');
            logContainer.innerHTML = '';
            progressBar.style.width = '0%';
            progressStatus.textContent = 'Starting...';

            const model = bulkModel.value;
            const qs = new URLSearchParams({ profile_url: url, model_size: model });
            eventSource = new EventSource('/api/bulk-transcribe?' + qs.toString());

            eventSource.onmessage = (e) => {
                const d = JSON.parse(e.data);

                switch (d.type) {
                    case 'status':
                        progressStatus.textContent = d.message;
                        addLog('i', 'info', d.message);
                        break;

                    case 'progress':
                        progressStatus.textContent = d.message;
                        progressBar.style.width = ((d.current / d.total) * 100) + '%';
                        break;

                    case 'transcribed':
                        progressBar.style.width = ((d.current / d.total) * 100) + '%';
                        addLog('\\u2713', 'success',
                            'Video #' + d.video_id + ' saved',
                            d.transcript);
                        break;

                    case 'reel_error':
                        addLog('!', 'error', 'Skipped reel ' + d.current, d.message);
                        break;

                    case 'duplicate':
                        addLog('\\u25A0', 'warning',
                            'Duplicate found (' + d.similarity + '% match with #' + d.matched_id + ')',
                            d.transcript);
                        progressBar.style.width = '100%';
                        summaryCard.classList.add('active');
                        summaryTitle.textContent = 'Stopped — Duplicate Found';
                        summaryText.textContent = d.message;
                        stopStream();
                        break;

                    case 'done':
                        progressBar.style.width = '100%';
                        summaryCard.classList.add('active');
                        summaryTitle.textContent = 'Complete';
                        summaryText.textContent = d.message;
                        stopStream();
                        break;

                    case 'error':
                        addLog('\\u2717', 'error', d.message);
                        stopStream();
                        break;
                }
            };

            eventSource.onerror = () => {
                addLog('\\u2717', 'error', 'Connection lost.');
                stopStream();
            };
        });

        stopBtn.addEventListener('click', () => {
            addLog('\\u25A0', 'warning', 'Stopped by user.');
            summaryCard.classList.add('active');
            summaryTitle.textContent = 'Stopped';
            summaryText.textContent = 'Bulk transcription was stopped manually.';
            stopStream();
        });
    </script>
</body>
</html>"""


def get_performance_html() -> str:
    """Return the performance database page HTML."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ContentMachine - Performance DB</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #f8fafc;
            --surface: #ffffff;
            --border: #e2e8f0;
            --border-strong: #cbd5e1;
            --text: #0f172a;
            --text-secondary: #475569;
            --text-muted: #94a3b8;
            --accent: #3b82f6;
            --accent-light: #eff6ff;
            --accent-hover: #2563eb;
            --danger: #ef4444;
            --danger-light: #fef2f2;
            --success: #10b981;
            --row-hover: #f1f5f9;
            --row-stripe: #f8fafc;
            --header-bg: #f1f5f9;
            --radius: 8px;
            --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
            --shadow-md: 0 4px 6px -1px rgba(0,0,0,0.07), 0 2px 4px -2px rgba(0,0,0,0.05);
            --shadow-lg: 0 10px 25px -5px rgba(0,0,0,0.1), 0 8px 10px -6px rgba(0,0,0,0.05);
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Inter', system-ui, -apple-system, sans-serif;
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
            font-size: 13px;
            -webkit-font-smoothing: antialiased;
        }
        .nav {
            display: flex; gap: 0.25rem; padding: 0.6rem 1.25rem;
            background: var(--surface); border-bottom: 1px solid var(--border);
            position: sticky; top: 0; z-index: 50;
            box-shadow: var(--shadow-sm);
        }
        .nav a {
            color: var(--text-secondary); text-decoration: none; padding: 0.4rem 0.85rem;
            font-size: 13px; font-weight: 500; border-radius: 6px;
            transition: all 0.15s ease;
        }
        .nav a:hover { color: var(--text); background: var(--header-bg); }
        .nav a.active { color: var(--accent); background: var(--accent-light); font-weight: 600; }

        .page-header {
            padding: 1.25rem 1.5rem;
            background: var(--surface);
            border-bottom: 1px solid var(--border);
        }
        .page-header h1 {
            font-size: 18px; font-weight: 700; color: var(--text);
            margin-bottom: 0.15rem;
        }
        .page-header p { font-size: 12px; color: var(--text-muted); }

        .stats-bar {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 1rem;
            padding: 1rem 1.5rem;
        }
        .stat-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 0.85rem 1rem;
            box-shadow: var(--shadow-sm);
        }
        .stat-card .stat-label {
            font-size: 11px; font-weight: 500; color: var(--text-muted);
            text-transform: uppercase; letter-spacing: 0.04em;
            margin-bottom: 0.3rem;
        }
        .stat-card .stat-value {
            font-size: 20px; font-weight: 700; color: var(--text);
            font-family: 'JetBrains Mono', monospace;
        }
        .stat-card .stat-unit {
            font-size: 11px; font-weight: 500; color: var(--text-muted); margin-left: 2px;
        }

        .toolbar-row {
            display: flex; align-items: center; justify-content: space-between;
            padding: 0.75rem 1.5rem;
            gap: 0.75rem; flex-wrap: wrap;
        }
        .toolbar-left { display: flex; align-items: center; gap: 0.5rem; }
        .toolbar-right { display: flex; align-items: center; gap: 0.5rem; }
        .search-input {
            padding: 0.45rem 0.75rem 0.45rem 2rem;
            border: 1px solid var(--border);
            border-radius: 6px;
            font-size: 13px; font-family: inherit;
            width: 240px; background: var(--surface);
            transition: border-color 0.15s;
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' fill='%2394a3b8' viewBox='0 0 16 16'%3E%3Cpath d='M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85zm-5.242.656a5 5 0 1 1 0-10 5 5 0 0 1 0 10z'/%3E%3C/svg%3E");
            background-repeat: no-repeat;
            background-position: 0.6rem center;
        }
        .search-input:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px rgba(59,130,246,0.1); }
        .row-count {
            font-size: 12px; color: var(--text-muted);
            font-family: 'JetBrains Mono', monospace;
        }
        .btn {
            display: inline-flex; align-items: center; gap: 0.35rem;
            padding: 0.45rem 0.85rem;
            border: 1px solid var(--border);
            border-radius: 6px;
            font-size: 12px; font-weight: 500; font-family: inherit;
            cursor: pointer; background: var(--surface);
            color: var(--text-secondary);
            transition: all 0.15s ease;
        }
        .btn:hover { background: var(--header-bg); border-color: var(--border-strong); color: var(--text); }
        .btn-primary {
            background: var(--accent); color: #fff; border-color: var(--accent);
        }
        .btn-primary:hover { background: var(--accent-hover); border-color: var(--accent-hover); color: #fff; }
        .replace-label {
            font-size: 12px; color: var(--text-muted);
            display: inline-flex; align-items: center; gap: 0.3rem; cursor: pointer;
            user-select: none;
        }
        .replace-label input { accent-color: var(--accent); }

        .table-container {
            margin: 0 1.5rem 1.5rem;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            overflow: hidden;
            box-shadow: var(--shadow-sm);
        }
        .table-scroll { overflow-x: auto; }
        table {
            width: 100%; border-collapse: collapse;
            font-size: 13px;
        }
        thead { position: sticky; top: 0; z-index: 5; }
        th {
            text-align: left;
            padding: 0.6rem 0.85rem;
            background: var(--header-bg);
            border-bottom: 2px solid var(--border);
            font-weight: 600; font-size: 11px;
            text-transform: uppercase; letter-spacing: 0.05em;
            color: var(--text-secondary);
            white-space: nowrap;
            user-select: none;
        }
        td {
            padding: 0.55rem 0.85rem;
            border-bottom: 1px solid var(--border);
            vertical-align: top;
        }
        tbody tr { transition: background 0.1s ease; cursor: pointer; }
        tbody tr:nth-child(even) { background: var(--row-stripe); }
        tbody tr:hover { background: var(--row-hover); }
        .col-id {
            width: 50px; text-align: center; color: var(--text-muted);
            font-family: 'JetBrains Mono', monospace; font-size: 12px;
        }
        .col-num {
            width: 90px; text-align: right;
            font-family: 'JetBrains Mono', monospace; font-size: 12px;
        }
        .col-transcript {
            min-width: 280px; max-width: 420px;
            overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
            color: var(--text); font-size: 12px; line-height: 1.5;
        }
        .null-val {
            color: var(--text-muted); font-style: italic; font-size: 11px;
        }

        .file-input { display: none; }

        .modal-overlay {
            display: none; position: fixed; inset: 0;
            background: rgba(15,23,42,0.4); backdrop-filter: blur(4px);
            z-index: 100; align-items: center; justify-content: center; padding: 1rem;
        }
        .modal-overlay.open { display: flex; }
        .modal-box {
            background: var(--surface);
            border-radius: 12px;
            max-width: 580px; width: 100%;
            max-height: 90vh; overflow-y: auto;
            box-shadow: var(--shadow-lg);
            animation: modalIn 0.2s ease;
        }
        @keyframes modalIn { from { opacity:0; transform: translateY(8px) scale(0.98); } to { opacity:1; transform: none; } }
        .modal-header {
            padding: 1rem 1.25rem;
            border-bottom: 1px solid var(--border);
            display: flex; align-items: center; justify-content: space-between;
        }
        .modal-header h2 { font-size: 15px; font-weight: 600; }
        .modal-close {
            width: 28px; height: 28px; border: none; background: none;
            color: var(--text-muted); cursor: pointer; border-radius: 6px;
            display: flex; align-items: center; justify-content: center;
            font-size: 18px; transition: all 0.15s;
        }
        .modal-close:hover { background: var(--header-bg); color: var(--text); }
        .modal-body { padding: 1.25rem; }
        .modal-body label {
            display: block; font-size: 11px; font-weight: 600;
            color: var(--text-secondary); margin-bottom: 0.3rem;
            text-transform: uppercase; letter-spacing: 0.04em;
        }
        .modal-body textarea {
            width: 100%; min-height: 80px; padding: 0.55rem 0.75rem;
            border: 1px solid var(--border); border-radius: 6px;
            font-family: 'JetBrains Mono', monospace; font-size: 12px;
            margin-bottom: 1rem; resize: vertical; line-height: 1.5;
            transition: border-color 0.15s;
        }
        .modal-body textarea:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px rgba(59,130,246,0.1); }
        .modal-body .field-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.75rem; }
        .modal-body .field-grid input {
            width: 100%; padding: 0.45rem 0.65rem;
            border: 1px solid var(--border); border-radius: 6px;
            font-family: 'JetBrains Mono', monospace; font-size: 12px;
            transition: border-color 0.15s;
        }
        .modal-body .field-grid input:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px rgba(59,130,246,0.1); }
        .modal-footer {
            padding: 0.85rem 1.25rem;
            border-top: 1px solid var(--border);
            display: flex; gap: 0.5rem; justify-content: flex-end;
        }
        .modal-footer .btn-danger {
            background: var(--danger-light); color: var(--danger);
            border-color: #fecaca; margin-right: auto;
        }
        .modal-footer .btn-danger:hover { background: #fee2e2; }

        @media (max-width: 640px) {
            .stats-bar { grid-template-columns: repeat(2, 1fr); }
            .toolbar-row { flex-direction: column; align-items: stretch; }
            .search-input { width: 100%; }
        }
    </style>
</head>
<body>
    <nav class="nav">
        <a href="/">Transcribe</a>
        <a href="/teleprompter">Teleprompter</a>
        <a href="/performance" class="active">Performance</a>
        <a href="/bulk">Bulk Transcribe</a>
    </nav>

    <div class="page-header">
        <h1>Performance Tracker</h1>
        <p>Historical video performance data</p>
    </div>

    <div class="stats-bar" id="statsBar">
        <div class="stat-card"><div class="stat-label">Total Videos</div><div class="stat-value" id="statTotal">--</div></div>
        <div class="stat-card"><div class="stat-label">Avg Views</div><div class="stat-value" id="statViews">--</div></div>
        <div class="stat-card"><div class="stat-label">Avg Skip Rate</div><div class="stat-value" id="statSkip">--<span class="stat-unit">%</span></div></div>
        <div class="stat-card"><div class="stat-label">Avg Retention</div><div class="stat-value" id="statRetention">--<span class="stat-unit">%</span></div></div>
    </div>

    <div class="toolbar-row">
        <div class="toolbar-left">
            <input type="search" class="search-input" id="search" placeholder="Search transcripts...">
            <span class="row-count" id="rowCount"></span>
        </div>
        <div class="toolbar-right">
            <button class="btn" id="importBtn">Import CSV</button>
            <label class="replace-label"><input type="checkbox" id="replaceCheck"> Replace all</label>
            <input type="file" id="fileInput" class="file-input" accept=".csv">
            <button class="btn btn-primary" id="addBtn">+ Add Video</button>
        </div>
    </div>

    <div class="table-container">
        <div class="table-scroll">
            <table>
                <thead>
                    <tr>
                        <th class="col-id">#</th>
                        <th class="col-transcript">Transcript</th>
                        <th class="col-num">Views</th>
                        <th class="col-num">Skip %</th>
                        <th class="col-num">Like %</th>
                        <th class="col-num">Retention %</th>
                    </tr>
                </thead>
                <tbody id="videoList"></tbody>
            </table>
        </div>
    </div>

    <div class="modal-overlay" id="modal">
        <div class="modal-box">
            <div class="modal-header">
                <h2 id="modalTitle">Edit Record</h2>
                <button class="modal-close" id="cancelBtn">&times;</button>
            </div>
            <div class="modal-body">
                <input type="hidden" id="editId">
                <label>Transcript</label>
                <textarea id="editTranscript" placeholder="Paste transcript..."></textarea>
                <div class="field-grid">
                    <div><label>Views</label><input type="number" id="editViews" placeholder="--"></div>
                    <div><label>Skip Rate %</label><input type="number" step="0.01" id="editSkipRate" placeholder="--"></div>
                    <div><label>Like Rate %</label><input type="number" step="0.01" id="editLikeRate" placeholder="--"></div>
                    <div><label>Share Rate %</label><input type="number" step="0.01" id="editShareRate" placeholder="--"></div>
                    <div><label>Comment Rate %</label><input type="number" step="0.01" id="editCommentRate" placeholder="--"></div>
                    <div><label>Save Rate %</label><input type="number" step="0.01" id="editSaveRate" placeholder="--"></div>
                    <div><label>Retention %</label><input type="number" step="0.01" id="editRetention" placeholder="--"></div>
                </div>
            </div>
            <div class="modal-footer">
                <button class="btn btn-danger" id="deleteBtn">Delete</button>
                <button class="btn" id="cancelBtn2">Cancel</button>
                <button class="btn btn-primary" id="saveBtn">Save</button>
            </div>
        </div>
    </div>

    <script>
        const searchEl = document.getElementById('search');
        const importBtn = document.getElementById('importBtn');
        const fileInput = document.getElementById('fileInput');
        const addBtn = document.getElementById('addBtn');
        const videoList = document.getElementById('videoList');
        const rowCount = document.getElementById('rowCount');
        const modal = document.getElementById('modal');
        const editId = document.getElementById('editId');
        const editTranscript = document.getElementById('editTranscript');
        const editViews = document.getElementById('editViews');
        const editSkipRate = document.getElementById('editSkipRate');
        const editLikeRate = document.getElementById('editLikeRate');
        const editShareRate = document.getElementById('editShareRate');
        const editCommentRate = document.getElementById('editCommentRate');
        const editSaveRate = document.getElementById('editSaveRate');
        const editRetention = document.getElementById('editRetention');
        const saveBtn = document.getElementById('saveBtn');
        const deleteBtn = document.getElementById('deleteBtn');
        const cancelBtn = document.getElementById('cancelBtn');
        const cancelBtn2 = document.getElementById('cancelBtn2');

        function num(v) { return v != null && v !== '' ? Number(v) : null; }

        async function loadVideos() {
            const q = searchEl.value;
            const res = await fetch('/api/videos?search=' + encodeURIComponent(q));
            const data = await res.json();
            renderVideos(data.videos);
        }

        async function loadStats() {
            const res = await fetch('/api/stats');
            const d = await res.json();
            document.getElementById('statTotal').textContent = d.total != null ? d.total.toLocaleString() : '--';
            document.getElementById('statViews').textContent = d.avg_views != null ? Math.round(d.avg_views).toLocaleString() : '--';
            const skipEl = document.getElementById('statSkip');
            skipEl.innerHTML = d.avg_skip_rate != null ? d.avg_skip_rate.toFixed(1) + '<span class="stat-unit">%</span>' : '--';
            const retEl = document.getElementById('statRetention');
            retEl.innerHTML = d.avg_retention != null ? d.avg_retention.toFixed(1) + '<span class="stat-unit">%</span>' : '--';
        }

        function esc(s) { return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

        function numCell(val) {
            if (val == null || val === '') return '<td class="col-num null-val">--</td>';
            return '<td class="col-num">' + esc(String(val)) + '</td>';
        }

        function renderVideos(videos) {
            rowCount.textContent = videos.length + ' row' + (videos.length !== 1 ? 's' : '');
            videoList.innerHTML = videos.map(v => {
                const t = v.transcript || '';
                const viewsStr = v.views != null ? Number(v.views).toLocaleString() : null;
                return '<tr data-id="' + v.id + '">'
                    + '<td class="col-id">' + v.id + '</td>'
                    + '<td class="col-transcript">' + esc(t.slice(0, 100)) + (t.length > 100 ? '...' : '') + '</td>'
                    + numCell(viewsStr)
                    + numCell(v.skip_rate)
                    + numCell(v.like_rate)
                    + numCell(v.retention_pct)
                    + '</tr>';
            }).join('');
            videoList.querySelectorAll('tr').forEach(row => {
                row.addEventListener('click', () => openEdit(parseInt(row.dataset.id)));
            });
        }

        function openEdit(id) {
            if (id) {
                fetch('/api/videos/' + id).then(r => r.json()).then(v => {
                    editId.value = v.id;
                    document.getElementById('modalTitle').textContent = 'Edit Video #' + v.id;
                    editTranscript.value = v.transcript || '';
                    editViews.value = v.views ?? '';
                    editSkipRate.value = v.skip_rate ?? '';
                    editLikeRate.value = v.like_rate ?? '';
                    editShareRate.value = v.share_rate ?? '';
                    editCommentRate.value = v.comment_rate ?? '';
                    editSaveRate.value = v.save_rate ?? '';
                    editRetention.value = v.retention_pct ?? '';
                    deleteBtn.style.display = '';
                    modal.classList.add('open');
                });
            } else {
                editId.value = '';
                document.getElementById('modalTitle').textContent = 'Add Video';
                editTranscript.value = editViews.value = editSkipRate.value = editLikeRate.value = editShareRate.value = editCommentRate.value = editSaveRate.value = editRetention.value = '';
                deleteBtn.style.display = 'none';
                modal.classList.add('open');
            }
        }

        function closeModal() { modal.classList.remove('open'); }

        async function saveVideo() {
            const id = editId.value;
            const body = {
                transcript: editTranscript.value,
                views: num(editViews.value),
                skip_rate: num(editSkipRate.value),
                like_rate: num(editLikeRate.value),
                share_rate: num(editShareRate.value),
                comment_rate: num(editCommentRate.value),
                save_rate: num(editSaveRate.value),
                retention_pct: num(editRetention.value),
            };
            if (id) {
                await fetch('/api/videos/' + id, { method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) });
            } else {
                await fetch('/api/videos', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) });
            }
            closeModal();
            loadAll();
        }

        async function deleteVideo() {
            if (!confirm('Delete this record?')) return;
            await fetch('/api/videos/' + editId.value, { method: 'DELETE' });
            closeModal();
            loadAll();
        }

        function loadAll() { loadVideos(); loadStats(); }

        importBtn.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', async (e) => {
            const file = e.target.files?.[0];
            if (!file) return;
            const fd = new FormData();
            fd.append('file', file);
            fd.append('replace', document.getElementById('replaceCheck').checked ? 'true' : 'false');
            const res = await fetch('/api/import', { method: 'POST', body: fd });
            const data = await res.json();
            alert('Imported ' + data.imported + ' videos.' + (data.errors?.length ? ' Errors: ' + data.errors.join(', ') : ''));
            fileInput.value = '';
            loadAll();
        });

        addBtn.addEventListener('click', () => openEdit(null));
        saveBtn.addEventListener('click', saveVideo);
        deleteBtn.addEventListener('click', deleteVideo);
        cancelBtn.addEventListener('click', closeModal);
        cancelBtn2.addEventListener('click', closeModal);
        modal.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });
        searchEl.addEventListener('input', () => { clearTimeout(window._searchT); window._searchT = setTimeout(loadVideos, 300); });

        loadAll();
    </script>
</body>
</html>"""
