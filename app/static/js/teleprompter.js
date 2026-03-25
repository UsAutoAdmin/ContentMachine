const textEl = document.getElementById('teleprompterText');
const displayEl = document.getElementById('teleprompterDisplay');
const speedEl = document.getElementById('speed');
const startBtn = document.getElementById('startTeleprompter');
const stopBtn = document.getElementById('stopTeleprompter');
let timer = null;
let pos = 0;

startBtn?.addEventListener('click', () => {
  const text = textEl.value.trim();
  if (!text) return;
  displayEl.textContent = text;
  pos = 0;
  clearInterval(timer);
  timer = setInterval(() => {
    pos += Number(speedEl.value) / 10;
    displayEl.scrollTop = pos;
  }, 100);
});

stopBtn?.addEventListener('click', () => clearInterval(timer));
