const chatLog = document.getElementById('chatLog');
const chatForm = document.getElementById('chatForm');
const chatInput = document.getElementById('chatInput');
const taskList = document.getElementById('taskList');
const messageCount = document.getElementById('messageCount');
const taskCount = document.getElementById('taskCount');
const lastUpdated = document.getElementById('lastUpdated');

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function renderMessages(messages = []) {
  chatLog.innerHTML = '';
  if (!messages.length) {
    addMessage('assistant', 'I’m here. Use this space as the operating console.');
    return;
  }
  messages.forEach((msg) => addMessage(msg.role, msg.body));
}

function addMessage(role, body) {
  const wrap = el('div', `message ${role === 'assistant' ? 'assistant' : 'user'}`);
  wrap.appendChild(el('div', 'message-role', role === 'assistant' ? 'Chud' : 'You'));
  wrap.appendChild(el('div', 'message-body', body));
  chatLog.appendChild(wrap);
  chatLog.scrollTop = chatLog.scrollHeight;
}

function renderTasks(tasks = []) {
  taskList.innerHTML = '';
  if (!tasks.length) {
    taskList.appendChild(el('div', 'lane', 'No tasks yet. Try: add task tighten dashboard QA flow'));
    return;
  }
  tasks.slice().reverse().forEach((task) => {
    const row = el('div', 'lane');
    row.innerHTML = `<strong>#${task.id} [${task.status}] ${task.title}</strong><span>${task.created_at || ''}</span>`;
    taskList.appendChild(row);
  });
}

function renderState(state) {
  renderMessages(state.messages || []);
  renderTasks(state.tasks || []);
  messageCount.textContent = String((state.messages || []).length);
  taskCount.textContent = String((state.tasks || []).length);
  lastUpdated.textContent = state.last_updated || '—';
}

async function loadState() {
  const res = await fetch('/api/command-state');
  const state = await res.json();
  renderState(state);
}

chatForm?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const text = chatInput.value.trim();
  if (!text) return;
  chatInput.value = '';
  const res = await fetch('/api/command', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: text }),
  });
  const data = await res.json();
  renderState(data.state || {});
});

loadState();
