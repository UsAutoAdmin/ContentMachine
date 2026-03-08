"""
ContentMachine - Instagram Reel Transcription Tool

Internal tool to paste an Instagram reel URL and get a transcription.
"""

import os
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
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
    </div>
    <script>
        const form = document.getElementById('form');
        const resultEl = document.getElementById('result');
        const insightsEl = document.getElementById('insights');
        const statusEl = document.getElementById('status');
        const submitBtn = document.getElementById('submit');

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
    </script>
</body>
</html>"""


def get_nav_html(active: str) -> str:
    """Navigation links for ContentMachine."""
    transcribe_cls = 'active' if active == 'transcribe' else ''
    teleprompter_cls = 'active' if active == 'teleprompter' else ''
    return f'''
    <nav class="nav">
        <a href="/" class="{transcribe_cls}">Transcribe</a>
        <a href="/teleprompter" class="{teleprompter_cls}">Teleprompter</a>
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


def get_performance_html() -> str:
    """Return the performance database page HTML."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ContentMachine - Performance DB</title>
    <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'IBM Plex Sans', system-ui, sans-serif;
            background: #f4f4f5;
            color: #18181b;
            min-height: 100vh;
            font-size: 13px;
        }
        .nav {
            display: flex; gap: 0.25rem; padding: 0.5rem 1rem;
            background: #e4e4e7; border-bottom: 1px solid #d4d4d8;
        }
        .nav a {
            color: #52525b; text-decoration: none; padding: 0.35rem 0.75rem;
            font-size: 12px; font-weight: 500;
        }
        .nav a:hover { color: #18181b; background: #d4d4d8; }
        .nav a.active { color: #18181b; background: #fff; border: 1px solid #d4d4d8; }
        .db-header {
            background: #fff;
            border-bottom: 1px solid #d4d4d8;
            padding: 0.75rem 1rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 0.5rem;
        }
        .db-header h1 { font-size: 14px; font-weight: 600; color: #3f3f46; }
        .db-header .meta { font-size: 11px; color: #71717a; font-family: 'IBM Plex Mono', monospace; }
        .toolbar { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }
        .toolbar input[type="search"] {
            padding: 0.35rem 0.5rem;
            border: 1px solid #d4d4d8;
            font-size: 12px;
            font-family: 'IBM Plex Mono', monospace;
            width: 180px;
        }
        .toolbar button {
            padding: 0.35rem 0.6rem;
            background: #e4e4e7;
            border: 1px solid #d4d4d8;
            font-size: 12px;
            cursor: pointer;
            font-family: inherit;
        }
        .toolbar button:hover { background: #d4d4d8; }
        .table-wrap {
            overflow-x: auto;
            background: #fff;
            margin: 0 1rem 1rem;
            border: 1px solid #d4d4d8;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
            font-family: 'IBM Plex Mono', monospace;
        }
        th {
            text-align: left;
            padding: 0.4rem 0.6rem;
            background: #f4f4f5;
            border-bottom: 1px solid #d4d4d8;
            font-weight: 600;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.02em;
            color: #52525b;
        }
        td {
            padding: 0.4rem 0.6rem;
            border-bottom: 1px solid #e4e4e7;
            vertical-align: top;
        }
        tr:hover td { background: #fafafa; }
        tr.row-clickable { cursor: pointer; }
        .col-id { width: 48px; text-align: right; color: #71717a; }
        .col-views, .col-skip, .col-like, .col-retention { width: 72px; text-align: right; }
        .col-transcript { max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; color: #3f3f46; }
        .null-val { color: #a1a1aa; }
        .modal {
            display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 100;
            align-items: center; justify-content: center; padding: 1rem;
        }
        .modal.open { display: flex; }
        .modal-content {
            background: #fff;
            border: 1px solid #d4d4d8;
            max-width: 560px;
            width: 100%;
            max-height: 90vh;
            overflow-y: auto;
            padding: 1rem;
        }
        .modal-content h2 { margin-bottom: 0.75rem; font-size: 13px; font-weight: 600; }
        .modal-content label { display: block; font-size: 11px; color: #71717a; margin-bottom: 0.2rem; }
        .modal-content textarea {
            width: 100%; min-height: 80px; padding: 0.5rem;
            border: 1px solid #d4d4d8; font-family: 'IBM Plex Mono', monospace; font-size: 12px;
            margin-bottom: 0.75rem;
        }
        .modal-content input {
            width: 100%; padding: 0.35rem 0.5rem;
            border: 1px solid #d4d4d8; font-family: 'IBM Plex Mono', monospace; font-size: 12px;
            margin-bottom: 0.75rem;
        }
        .modal-content .row { display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.5rem 1rem; }
        .modal-content .actions { margin-top: 0.75rem; display: flex; gap: 0.5rem; }
        .modal-content button {
            padding: 0.35rem 0.6rem;
            background: #e4e4e7;
            border: 1px solid #d4d4d8;
            font-size: 12px;
            cursor: pointer;
            font-family: inherit;
        }
        .modal-content button:hover { background: #d4d4d8; }
        .modal-content button.danger { background: #fef2f2; border-color: #fecaca; color: #b91c1c; }
        .modal-content button.danger:hover { background: #fee2e2; }
        .file-input { display: none; }
    </style>
</head>
<body>
    <nav class="nav">
        <a href="/">Transcribe</a>
        <a href="/teleprompter">Teleprompter</a>
        <a href="/performance" class="active">Performance</a>
    </nav>
    <div class="db-header">
        <div>
            <h1>videos</h1>
            <span class="meta" id="tableMeta">—</span>
        </div>
        <div class="toolbar">
            <input type="search" id="search" placeholder="Search transcript">
            <button id="importBtn">Import CSV</button>
            <label style="font-size:11px;color:#71717a;display:inline-flex;align-items:center;gap:0.25rem;"><input type="checkbox" id="replaceCheck"> Replace all</label>
            <input type="file" id="fileInput" class="file-input" accept=".csv">
            <button id="addBtn">+ Insert</button>
        </div>
    </div>
    <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th class="col-id">id</th>
                    <th class="col-transcript">transcript</th>
                    <th class="col-views">views</th>
                    <th class="col-skip">skip_rate</th>
                    <th class="col-like">like_rate</th>
                    <th class="col-retention">retention_pct</th>
                </tr>
            </thead>
            <tbody id="videoList"></tbody>
        </table>
    </div>
    <div class="modal" id="modal">
        <div class="modal-content">
            <h2 id="modalTitle">Edit Record</h2>
            <input type="hidden" id="editId">
            <label>transcript</label>
            <textarea id="editTranscript"></textarea>
            <div class="row">
                <div><label>views</label><input type="number" id="editViews" placeholder="NULL"></div>
                <div><label>skip_rate</label><input type="number" step="0.01" id="editSkipRate" placeholder="NULL"></div>
                <div><label>like_rate</label><input type="number" step="0.01" id="editLikeRate" placeholder="NULL"></div>
                <div><label>share_rate</label><input type="number" step="0.01" id="editShareRate" placeholder="NULL"></div>
                <div><label>comment_rate</label><input type="number" step="0.01" id="editCommentRate" placeholder="NULL"></div>
                <div><label>save_rate</label><input type="number" step="0.01" id="editSaveRate" placeholder="NULL"></div>
                <div><label>retention_pct</label><input type="number" step="0.01" id="editRetention" placeholder="NULL"></div>
            </div>
            <div class="actions">
                <button id="saveBtn">UPDATE</button>
                <button class="danger" id="deleteBtn">DELETE</button>
                <button id="cancelBtn">Cancel</button>
            </div>
        </div>
    </div>
    <script>
        const searchEl = document.getElementById('search');
        const importBtn = document.getElementById('importBtn');
        const fileInput = document.getElementById('fileInput');
        const addBtn = document.getElementById('addBtn');
        const videoList = document.getElementById('videoList');
        const tableMeta = document.getElementById('tableMeta');
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

        function fmt(v) { return v != null && v !== '' ? v : '—'; }
        function num(v) { return v != null && v !== '' ? Number(v) : null; }

        async function loadVideos() {
            const q = searchEl.value;
            const res = await fetch('/api/videos?search=' + encodeURIComponent(q));
            const data = await res.json();
            renderVideos(data.videos);
        }

        async function loadStats() {
            const res = await fetch('/api/stats');
            const data = await res.json();
            const avgViews = data.avg_views ? Math.round(data.avg_views).toLocaleString() : 'NULL';
            const avgSkip = data.avg_skip_rate != null ? data.avg_skip_rate.toFixed(1) : 'NULL';
            const avgLike = data.avg_like_rate != null ? data.avg_like_rate.toFixed(2) : 'NULL';
            const avgRet = data.avg_retention != null ? data.avg_retention.toFixed(1) : 'NULL';
            tableMeta.textContent = `${fmt(data.total)} rows | AVG(views)=${avgViews} AVG(skip_rate)=${avgSkip} AVG(like_rate)=${avgLike} AVG(retention_pct)=${avgRet}`;
        }

        function esc(s) { return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
        function cell(val, cls) {
            if (val == null || val === '') return '<td class="null-val">NULL</td>';
            return '<td' + (cls ? ' class="' + cls + '"' : '') + '>' + esc(String(val)) + '</td>';
        }

        function renderVideos(videos) {
            videoList.innerHTML = videos.map(v => {
                const t = v.transcript || '';
                return `<tr class="row-clickable" data-id="${v.id}">
                    <td class="col-id">${v.id}</td>
                    <td class="col-transcript">${esc(t.slice(0, 80))}${t.length > 80 ? '…' : ''}</td>
                    ${cell(v.views != null ? Number(v.views).toLocaleString() : null, 'col-views')}
                    ${cell(v.skip_rate != null ? v.skip_rate : null, 'col-skip')}
                    ${cell(v.like_rate != null ? v.like_rate : null, 'col-like')}
                    ${cell(v.retention_pct != null ? v.retention_pct : null, 'col-retention')}
                </tr>`;
            }).join('');
            videoList.querySelectorAll('.row-clickable').forEach(row => {
                row.addEventListener('click', () => openEdit(parseInt(row.dataset.id)));
            });
        }

        function openEdit(id) {
            if (id) {
                fetch('/api/videos/' + id).then(r => r.json()).then(v => {
                    editId.value = v.id;
                    document.getElementById('modalTitle').textContent = 'Edit id=' + v.id;
                    editTranscript.value = v.transcript || '';
                    editViews.value = v.views ?? '';
                    editSkipRate.value = v.skip_rate ?? '';
                    editLikeRate.value = v.like_rate ?? '';
                    editShareRate.value = v.share_rate ?? '';
                    editCommentRate.value = v.comment_rate ?? '';
                    editSaveRate.value = v.save_rate ?? '';
                    editRetention.value = v.retention_pct ?? '';
                    deleteBtn.style.display = 'inline-block';
                    modal.classList.add('open');
                });
            } else {
                editId.value = '';
                document.getElementById('modalTitle').textContent = 'Insert';
                editTranscript.value = editViews.value = editSkipRate.value = editLikeRate.value = editShareRate.value = editCommentRate.value = editSaveRate.value = editRetention.value = '';
                deleteBtn.style.display = 'none';
                modal.classList.add('open');
            }
        }

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
            modal.classList.remove('open');
            loadAll();
        }

        async function deleteVideo() {
            if (!confirm('Delete this record?')) return;
            await fetch('/api/videos/' + editId.value, { method: 'DELETE' });
            modal.classList.remove('open');
            loadAll();
        }

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
        cancelBtn.addEventListener('click', () => modal.classList.remove('open'));
        searchEl.addEventListener('input', () => { clearTimeout(window._searchT); window._searchT = setTimeout(loadVideos, 300); });

        loadAll();
    </script>
</body>
</html>"""
