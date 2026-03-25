const form = document.getElementById('transcribeForm');
const statusEl = document.getElementById('transcribeStatus');
const resultEl = document.getElementById('transcribeResult');
const insightsEl = document.getElementById('insights');
const submitBtn = document.getElementById('submitBtn');

function formatCount(v) {
  if (v == null) return '—';
  if (v >= 1e6) return (v / 1e6).toFixed(1) + 'M';
  if (v >= 1e3) return (v / 1e3).toFixed(1) + 'K';
  return String(v);
}

form?.addEventListener('submit', async (e) => {
  e.preventDefault();
  submitBtn.disabled = true;
  statusEl.textContent = 'Downloading and transcribing...';
  resultEl.classList.add('hidden');
  insightsEl.innerHTML = '';
  try {
    const fd = new FormData();
    fd.append('url', document.getElementById('url').value);
    fd.append('model_size', document.getElementById('model').value);
    const res = await fetch('/transcribe', { method: 'POST', body: fd });
    const data = await res.json();
    if (!res.ok || !data.success) throw new Error(data.detail || 'Transcription failed');
    const i = data.insights || {};
    insightsEl.innerHTML = `
      <div class="insight-chip">Views: ${formatCount(i.view_count)}</div>
      <div class="insight-chip">Likes: ${formatCount(i.like_count)}</div>
      <div class="insight-chip">Comments: ${formatCount(i.comment_count)}</div>`;
    resultEl.textContent = data.transcription;
    resultEl.classList.remove('hidden');
    statusEl.textContent = 'Done.';
  } catch (err) {
    statusEl.textContent = err.message || 'Error';
  } finally {
    submitBtn.disabled = false;
  }
});
