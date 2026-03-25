const searchEl = document.getElementById('search');
const importBtn = document.getElementById('importBtn');
const fileInput = document.getElementById('fileInput');
const addBtn = document.getElementById('addBtn');
const videoList = document.getElementById('videoList');
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

function num(v) { return v != null && v !== '' ? Number(v) : null; }
function esc(s) { return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function numCell(val) { return val == null || val === '' ? '<td>--</td>' : `<td>${esc(String(val))}</td>`; }
function closeModal() { modal.classList.remove('open'); }

async function loadVideos() {
  const res = await fetch('/api/videos?search=' + encodeURIComponent(searchEl.value || ''));
  const data = await res.json();
  const videos = data.videos || [];
  videoList.innerHTML = videos.map(v => {
    const t = v.transcript || '';
    return `<tr data-id="${v.id}"><td>${v.id}</td><td>${esc(t.slice(0, 100))}${t.length > 100 ? '...' : ''}</td><td>${v.views ?? '--'}</td><td>${v.skip_rate ?? '--'}</td><td>${v.like_rate ?? '--'}</td><td>${v.retention_pct ?? '--'}</td></tr>`;
  }).join('');
  videoList.querySelectorAll('tr').forEach(row => row.addEventListener('click', () => openEdit(parseInt(row.dataset.id))));
}

async function loadStats() {
  const res = await fetch('/api/stats');
  const d = await res.json();
  document.getElementById('statTotal').textContent = d.total != null ? d.total.toLocaleString() : '--';
  document.getElementById('statViews').textContent = d.avg_views != null ? Math.round(d.avg_views).toLocaleString() : '--';
  document.getElementById('statSkip').textContent = d.avg_skip_rate != null ? d.avg_skip_rate.toFixed(1) + '%' : '--';
  document.getElementById('statRetention').textContent = d.avg_retention != null ? d.avg_retention.toFixed(1) + '%' : '--';
}

function openEdit(id) {
  if (id) {
    fetch('/api/videos/' + id).then(r => r.json()).then(v => {
      editId.value = v.id; editTranscript.value = v.transcript || ''; editViews.value = v.views ?? '';
      editSkipRate.value = v.skip_rate ?? ''; editLikeRate.value = v.like_rate ?? ''; editShareRate.value = v.share_rate ?? '';
      editCommentRate.value = v.comment_rate ?? ''; editSaveRate.value = v.save_rate ?? ''; editRetention.value = v.retention_pct ?? '';
      deleteBtn.style.display = ''; modal.classList.add('open');
    });
  } else {
    editId.value = ''; editTranscript.value = editViews.value = editSkipRate.value = editLikeRate.value = editShareRate.value = editCommentRate.value = editSaveRate.value = editRetention.value = '';
    deleteBtn.style.display = 'none'; modal.classList.add('open');
  }
}

async function saveVideo() {
  const id = editId.value;
  const body = { transcript: editTranscript.value, views: num(editViews.value), skip_rate: num(editSkipRate.value), like_rate: num(editLikeRate.value), share_rate: num(editShareRate.value), comment_rate: num(editCommentRate.value), save_rate: num(editSaveRate.value), retention_pct: num(editRetention.value) };
  if (id) await fetch('/api/videos/' + id, { method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) });
  else await fetch('/api/videos', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) });
  closeModal(); loadAll();
}

async function deleteVideo() {
  if (!confirm('Delete this record?')) return;
  await fetch('/api/videos/' + editId.value, { method: 'DELETE' });
  closeModal(); loadAll();
}

function loadAll() { loadVideos(); loadStats(); }
importBtn?.addEventListener('click', () => fileInput.click());
fileInput?.addEventListener('change', async (e) => {
  const file = e.target.files?.[0]; if (!file) return;
  const fd = new FormData(); fd.append('file', file); fd.append('replace', document.getElementById('replaceCheck').checked ? 'true' : 'false');
  const res = await fetch('/api/import', { method: 'POST', body: fd }); const data = await res.json();
  alert('Imported ' + data.imported + ' videos.'); fileInput.value = ''; loadAll();
});
addBtn?.addEventListener('click', () => openEdit(null));
saveBtn?.addEventListener('click', saveVideo); deleteBtn?.addEventListener('click', deleteVideo); cancelBtn?.addEventListener('click', closeModal);
modal?.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });
searchEl?.addEventListener('input', () => { clearTimeout(window._searchT); window._searchT = setTimeout(loadVideos, 300); });
loadAll();
