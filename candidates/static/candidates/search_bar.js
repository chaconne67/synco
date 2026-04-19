(function () {
  'use strict';

  const el = (id) => document.getElementById(id);
  const input = el('sb-input');
  const micBtn = el('sb-mic-btn');
  const sendBtn = el('sb-send-btn');
  const stopBtn = el('sb-stop-btn');
  const recWrap = el('sb-recording');
  const procWrap = el('sb-processing');
  const timerEl = el('sb-timer');
  const bars = document.querySelectorAll('.sb-bar');

  if (!input) return;

  let mediaRecorder = null;
  let audioChunks = [];
  let recordStart = 0;
  let timerId = null;
  let animId = null;
  let audioCtx = null;
  let sessionId = sessionStorage.getItem('synco_session_id') || null;

  function setState(s) {
    // idle | text | recording | processing
    input.classList.toggle('hidden', s === 'recording' || s === 'processing');
    recWrap.classList.toggle('hidden', s !== 'recording');
    recWrap.classList.toggle('flex', s === 'recording');
    procWrap.classList.toggle('hidden', s !== 'processing');
    procWrap.classList.toggle('flex', s === 'processing');
    micBtn.classList.toggle('hidden', s !== 'idle');
    sendBtn.classList.toggle('hidden', s !== 'text');
    stopBtn.classList.toggle('hidden', s !== 'recording');
  }

  input.addEventListener('focus', () => { if (input.value.trim()) setState('text'); });
  input.addEventListener('input', () => setState(input.value.trim() ? 'text' : 'idle'));
  input.addEventListener('blur', () => { if (!input.value.trim()) setState('idle'); });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.isComposing) { e.preventDefault(); sendQuery('text'); }
    if (e.key === 'Escape') { input.value = ''; input.blur(); setState('idle'); }
  });

  sendBtn.addEventListener('click', () => sendQuery('text'));
  micBtn.addEventListener('click', startRecording);
  stopBtn.addEventListener('click', stopRecording);

  async function sendQuery(inputType) {
    const q = input.value.trim();
    if (!q) return;
    setState('processing');
    try {
      const resp = await fetch(window.SEARCH_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': window.CSRF_TOKEN,
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: JSON.stringify({ message: q, session_id: sessionId, input_type: inputType || 'text' }),
      });
      if (!resp.ok) {
        console.error('search failed', resp.status);
        setState(input.value.trim() ? 'text' : 'idle');
        return;
      }
      const data = await resp.json();
      if (data.session_id) {
        sessionId = data.session_id;
        sessionStorage.setItem('synco_session_id', sessionId);
      }
      refreshList();
      input.value = '';
      setState('idle');
    } catch (err) {
      console.error(err);
      setState('idle');
    }
  }

  function refreshList() {
    if (typeof htmx === 'undefined') return;
    let url = '/candidates/';
    if (sessionId) url += '?session_id=' + encodeURIComponent(sessionId);
    const target = document.getElementById('search-area');
    if (!target) return;
    htmx.ajax('GET', url, { target: '#search-area', swap: 'innerHTML' });
  }

  async function startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm';
      mediaRecorder = new MediaRecorder(stream, { mimeType: mime });
      audioChunks = [];
      mediaRecorder.ondataavailable = (e) => audioChunks.push(e.data);
      mediaRecorder.onstop = onRecordingStopped;
      mediaRecorder.start();
      recordStart = Date.now();
      setState('recording');
      startTimer();
      startWaveform(stream);
      setTimeout(() => { if (mediaRecorder && mediaRecorder.state === 'recording') stopRecording(); }, 60000);
    } catch (err) {
      console.error('mic denied', err);
      alert('마이크 권한이 필요합니다.');
    }
  }

  function stopRecording() {
    if (!mediaRecorder) return;
    const elapsed = Date.now() - recordStart;
    if (elapsed < 500) {
      try { mediaRecorder.stop(); } catch (e) {}
      mediaRecorder.stream.getTracks().forEach(t => t.stop());
      cleanupRecording();
      setState('idle');
      return;
    }
    mediaRecorder.stop();
    mediaRecorder.stream.getTracks().forEach(t => t.stop());
    setState('processing');
  }

  function startTimer() {
    timerId = setInterval(() => {
      const sec = Math.floor((Date.now() - recordStart) / 1000);
      const mm = String(Math.floor(sec / 60)).padStart(2, '0');
      const ss = String(sec % 60).padStart(2, '0');
      timerEl.textContent = `${mm}:${ss}`;
    }, 200);
  }

  function startWaveform(stream) {
    try {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const src = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 64;
      src.connect(analyser);
      const data = new Uint8Array(analyser.frequencyBinCount);
      function tick() {
        analyser.getByteFrequencyData(data);
        bars.forEach((b, i) => {
          const v = data[i % data.length] / 255;
          b.style.height = Math.max(4, v * 24) + 'px';
        });
        animId = requestAnimationFrame(tick);
      }
      tick();
    } catch (e) { /* ignore */ }
  }

  function cleanupRecording() {
    if (timerId) { clearInterval(timerId); timerId = null; }
    if (animId) { cancelAnimationFrame(animId); animId = null; }
    if (audioCtx) { try { audioCtx.close(); } catch (e) {} audioCtx = null; }
    timerEl.textContent = '00:00';
  }

  async function onRecordingStopped() {
    cleanupRecording();
    const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType });
    const fd = new FormData();
    fd.append('audio', blob, 'recording.webm');
    fd.append('csrfmiddlewaretoken', window.CSRF_TOKEN);
    try {
      const resp = await fetch(window.VOICE_URL, {
        method: 'POST',
        body: fd,
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      });
      if (!resp.ok) {
        let errMsg = '음성 인식에 실패했습니다.';
        try { const d = await resp.json(); if (d && d.error) errMsg = d.error; } catch (e) {}
        alert(errMsg);
        setState('idle');
        return;
      }
      const data = await resp.json();
      if (data.text) {
        input.value = data.text;
        setState('text');
        await sendQuery('voice');
      } else {
        setState('idle');
      }
    } catch (err) {
      console.error(err);
      setState('idle');
    }
  }
})();
