const bulkForm = document.getElementById('bulkForm');
const bulkLog = document.getElementById('bulkLog');
const stopBulk = document.getElementById('stopBulk');
let eventSource = null;

function addLog(message) {
  const line = document.createElement('div');
  line.textContent = message;
  bulkLog.appendChild(line);
  bulkLog.scrollTop = bulkLog.scrollHeight;
}

bulkForm?.addEventListener('submit', (e) => {
  e.preventDefault();
  if (eventSource) eventSource.close();
  bulkLog.innerHTML = '';
  const qs = new URLSearchParams({ profile_url: document.getElementById('profileUrl').value, model_size: document.getElementById('bulkModel').value });
  eventSource = new EventSource('/api/bulk-transcribe?' + qs.toString());
  eventSource.onmessage = (evt) => {
    const data = JSON.parse(evt.data);
    addLog(data.message || JSON.stringify(data));
    if (data.type === 'done' || data.type === 'error' || data.type === 'duplicate') {
      eventSource.close();
      eventSource = null;
    }
  };
  eventSource.onerror = () => {
    addLog('Stream ended.');
    eventSource?.close();
    eventSource = null;
  };
});

stopBulk?.addEventListener('click', () => {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
    addLog('Stopped.');
  }
});
