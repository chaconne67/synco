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
  const chatPanel = el('sb-chat-panel');
  const chatLog = el('sb-chat-log');
  const closeBtn = el('sb-close-btn');

  if (!input) return;

  function showChatPanel() {
    if (!chatPanel) return;
    chatPanel.classList.remove('hidden');
    // next frame to trigger transition
    requestAnimationFrame(() => {
      chatPanel.classList.remove('opacity-0', 'translate-y-3');
    });
  }

  function scrollChatToBottom() {
    if (!chatPanel) return;
    chatPanel.scrollTop = chatPanel.scrollHeight;
  }

  function addUserBubble(text) {
    if (!chatLog) return;
    showChatPanel();
    const wrap = document.createElement('div');
    wrap.className = 'flex justify-end';
    const bubble = document.createElement('div');
    bubble.className = 'bg-ink3 text-white rounded-2xl rounded-tr-sm px-3.5 py-2 max-w-[85%] text-sm leading-relaxed whitespace-pre-wrap break-words';
    bubble.textContent = text;
    wrap.appendChild(bubble);
    chatLog.appendChild(wrap);
    scrollChatToBottom();
  }

  function addTypingBubble() {
    if (!chatLog) return null;
    showChatPanel();
    const wrap = document.createElement('div');
    wrap.className = 'flex justify-start';
    wrap.dataset.typing = '1';
    const bubble = document.createElement('div');
    bubble.className = 'bg-line rounded-2xl rounded-tl-sm px-3.5 py-2 text-sm text-muted flex items-center gap-2';
    bubble.innerHTML = '<span class="inline-flex gap-1">' +
      '<span class="w-1.5 h-1.5 bg-faint rounded-full animate-bounce" style="animation-delay:0ms"></span>' +
      '<span class="w-1.5 h-1.5 bg-faint rounded-full animate-bounce" style="animation-delay:150ms"></span>' +
      '<span class="w-1.5 h-1.5 bg-faint rounded-full animate-bounce" style="animation-delay:300ms"></span>' +
      '</span><span class="eyebrow">검색 중…</span>';
    wrap.appendChild(bubble);
    chatLog.appendChild(wrap);
    scrollChatToBottom();
    return wrap;
  }

  function removeTypingBubble(node) {
    if (node && node.parentNode) node.parentNode.removeChild(node);
  }

  function addAiBubble(text, resultCount) {
    if (!chatLog) return;
    showChatPanel();
    const wrap = document.createElement('div');
    wrap.className = 'flex justify-start';
    const bubble = document.createElement('div');
    bubble.className = 'bg-line rounded-2xl rounded-tl-sm px-3.5 py-2 max-w-[85%] text-sm text-ink leading-relaxed whitespace-pre-wrap break-words';
    const body = text || '결과를 확인해주세요.';
    bubble.textContent = body;
    if (typeof resultCount === 'number') {
      const meta = document.createElement('div');
      meta.className = 'mt-1.5 text-xs text-muted tnum';
      meta.textContent = `→ ${resultCount}명을 리스트에 표시합니다.`;
      bubble.appendChild(meta);
    }
    wrap.appendChild(bubble);
    chatLog.appendChild(wrap);
    scrollChatToBottom();
  }

  let mediaRecorder = null;
  let audioChunks = [];
  let recordStart = 0;
  let timerId = null;
  let animId = null;
  let autostopId = null;
  let isStopping = false;
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
  if (closeBtn) closeBtn.addEventListener('click', hideChatPanel);

  // 대화창 바깥 클릭 시 닫기 (검색 바 영역 클릭은 제외)
  document.addEventListener('click', (e) => {
    if (!chatPanel || chatPanel.classList.contains('hidden')) return;
    const wrapper = document.getElementById('search-bar-wrapper');
    if (wrapper && !wrapper.contains(e.target)) hideChatPanel();
  });

  function hideChatPanel() {
    if (!chatPanel) return;
    sessionStorage.setItem('synco_chat_dismissed', '1');
    chatPanel.classList.add('opacity-0', 'translate-y-3');
    setTimeout(() => chatPanel.classList.add('hidden'), 300);
  }

  async function restoreSessionHistory() {
    if (!sessionId || !window.SESSION_TURNS_URL_TEMPLATE) return;
    const dismissed = sessionStorage.getItem('synco_chat_dismissed') === '1';
    try {
      const url = window.SESSION_TURNS_URL_TEMPLATE.replace('__ID__', encodeURIComponent(sessionId));
      const resp = await fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
      if (!resp.ok) return;
      const data = await resp.json();
      if (!data.is_active || !Array.isArray(data.turns) || !data.turns.length) {
        sessionStorage.removeItem('synco_session_id');
        sessionStorage.removeItem('synco_chat_dismissed');
        sessionId = null;
        return;
      }
      if (dismissed) return;
      data.turns.forEach((t) => {
        if (t.user_text) addUserBubble(t.user_text);
        if (t.ai_response) addAiBubble(t.ai_response, typeof t.result_count === 'number' ? t.result_count : undefined);
      });
    } catch (e) { /* ignore */ }
  }

  restoreSessionHistory();

  async function sendQuery(inputType) {
    const q = input.value.trim();
    if (!q) return;
    sessionStorage.removeItem('synco_chat_dismissed');
    addUserBubble(q);
    input.value = '';
    setState('processing');
    const typingNode = addTypingBubble();
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
      removeTypingBubble(typingNode);
      if (!resp.ok) {
        let msg = '검색 처리 중 오류가 발생했습니다.';
        try { const d = await resp.json(); if (d && d.error) msg = d.error; } catch (e) {}
        addAiBubble(msg);
        setState('idle');
        return;
      }
      const data = await resp.json();
      if (data.session_id) {
        sessionId = data.session_id;
        sessionStorage.setItem('synco_session_id', sessionId);
      }
      addAiBubble(data.ai_message, typeof data.result_count === 'number' ? data.result_count : undefined);
      refreshList();
      setState('idle');
    } catch (err) {
      removeTypingBubble(typingNode);
      addAiBubble('네트워크 오류로 검색에 실패했습니다.');
      console.error(err);
      setState('idle');
    }
  }

  function refreshList() {
    if (typeof htmx === 'undefined') return;
    let url = '/candidates/';
    if (sessionId) url += '?session_id=' + encodeURIComponent(sessionId);
    const target = document.getElementById('search-area');
    if (target) {
      htmx.ajax('GET', url, { target: '#search-area', swap: 'innerHTML' });
    } else {
      // 다른 메뉴에서 호출된 경우: 후보자 리스트 페이지로 이동
      const main = document.getElementById('main-content');
      if (main) {
        htmx.ajax('GET', url, { target: '#main-content', swap: 'innerHTML' });
        try { history.pushState(null, '', url); } catch (e) {}
      } else {
        window.location.href = url;
      }
    }
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
      autostopId = setTimeout(() => { if (mediaRecorder && mediaRecorder.state === 'recording') stopRecording(); }, 60000);
    } catch (err) {
      console.error('mic denied', err);
      setState('idle');
      alert('마이크 권한이 필요합니다.');
    }
  }

  function stopRecording() {
    if (!mediaRecorder || isStopping) return;
    isStopping = true;
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
    if (autostopId) { clearTimeout(autostopId); autostopId = null; }
    if (timerId) { clearInterval(timerId); timerId = null; }
    if (animId) { cancelAnimationFrame(animId); animId = null; }
    if (audioCtx) { try { audioCtx.close(); } catch (e) {} audioCtx = null; }
    timerEl.textContent = '00:00';
    isStopping = false;
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
