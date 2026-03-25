const chatLog = document.getElementById('chatLog');
const chatForm = document.getElementById('chatForm');
const chatInput = document.getElementById('chatInput');

function addMessage(role, body) {
  const wrap = document.createElement('div');
  wrap.className = `message ${role}`;
  wrap.innerHTML = `<div class="message-role">${role === 'assistant' ? 'Chud' : 'You'}</div><div class="message-body"></div>`;
  wrap.querySelector('.message-body').textContent = body;
  chatLog.appendChild(wrap);
  chatLog.scrollTop = chatLog.scrollHeight;
}

chatForm?.addEventListener('submit', (e) => {
  e.preventDefault();
  const text = chatInput.value.trim();
  if (!text) return;
  addMessage('user', text);
  addMessage('assistant', 'Message captured inside ContentMachine. This front page is now the communication-first home. Next phase: wire this into real Chud task routing so requests here can directly drive work.');
  chatInput.value = '';
});
