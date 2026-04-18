/* synco chatbot — voice-first search */
(function () {
  "use strict";

  /* ── State ── */
  var urlParams = new URLSearchParams(window.location.search);
  var sessionId = urlParams.get("session_id") || sessionStorage.getItem("synco_session_id") || null;
  var mediaRecorder = null;
  var audioChunks = [];
  var isRecording = false;
  var isSearching = false;
  var searchPerformedSinceOpen = false;
  var recordingMimeType = "audio/webm";
  var MAX_RECORDING_SECONDS = 60;
  var MAX_BLOB_SIZE = 10 * 1024 * 1024;

  /* Audio visualization */
  var audioContext = null;
  var analyserNode = null;
  var vizRaf = null;
  var recTimerInterval = null;
  var recStartTime = null;

  /* ────────────────────────────────────────────
     Modal open / close with slide animation
     ──────────────────────────────────────────── */
  window.toggleChatbot = function () {
    var modal = document.getElementById("chatbot-modal");
    var overlay = document.getElementById("chatbot-overlay");
    var toggle = document.getElementById("chatbot-toggle");
    var isOpen = modal.dataset.open === "true";

    if (isOpen) {
      /* Close: slide down */
      modal.classList.remove("slide-open");
      modal.classList.add("slide-closed");
      overlay.classList.remove("opacity-100");
      overlay.classList.add("opacity-0");
      setTimeout(function () {
        modal.classList.add("hidden");
        overlay.classList.add("hidden");
        toggle.classList.remove("hidden");
      }, 300);
      modal.dataset.open = "false";
      stopMinimizeBlink();
      if (searchPerformedSinceOpen && sessionId && window.location.pathname !== "/candidates/") {
        window.location.href = "/candidates/?session_id=" + sessionId;
      } else if (searchPerformedSinceOpen && window.location.pathname === "/candidates/") {
        refreshCandidateList();
      }
    } else {
      /* Open: slide up with animation */
      modal.classList.remove("hidden");
      modal.classList.add("slide-closed");
      overlay.classList.remove("hidden");
      modal.offsetHeight; /* force reflow before animation */
      modal.classList.remove("slide-closed");
      modal.classList.add("slide-open");
      overlay.classList.remove("opacity-0");
      overlay.classList.add("opacity-100");
      toggle.classList.add("hidden");
      modal.dataset.open = "true";
      searchPerformedSinceOpen = false;
      if (sessionId) loadChatHistory(sessionId);
      scrollChat();
    }
  };

  /* ────────────────────────────────────────────
     Text input toggle
     ──────────────────────────────────────────── */
  window.showTextInput = function () {
    hide("voice-idle");
    show("text-input-area");
    var input = document.getElementById("chat-input");
    if (input) input.focus();
  };

  window.hideTextInput = function () {
    hide("text-input-area");
    show("voice-idle");
  };

  /* ────────────────────────────────────────────
     Chip search
     ──────────────────────────────────────────── */
  window.searchWithChip = function (text) {
    if (isSearching) return;
    appendUserMessage(text);
    appendThinking();
    doSearch(text, "text");
  };

  /* ────────────────────────────────────────────
     Text send
     ──────────────────────────────────────────── */
  window.sendMessage = function () {
    if (isSearching) return;
    var input = document.getElementById("chat-input");
    var text = input.value.trim();
    if (!text) return;
    input.value = "";
    appendUserMessage(text);
    appendThinking();
    doSearch(text, "text");
  };

  /* ────────────────────────────────────────────
     Recording — start / stop
     ──────────────────────────────────────────── */
  window.toggleRecording = function () {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  window.startRecording = startRecording;

  function startRecording() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      appendAIMessage("마이크를 사용하려면 HTTPS 또는 localhost로 접속해주세요. (현재 HTTP 접속은 브라우저가 마이크를 차단합니다)");
      switchVoiceState("idle");
      return;
    }
    navigator.mediaDevices
      .getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          sampleRate: 16000,
          channelCount: 1
        }
      })
      .then(function (stream) {
        audioChunks = [];
        recordingMimeType = detectMimeType();
        var opts = recordingMimeType ? { mimeType: recordingMimeType, audioBitsPerSecond: 128000 } : { audioBitsPerSecond: 128000 };
        mediaRecorder = new MediaRecorder(stream, opts);
        recordingMimeType = mediaRecorder.mimeType || recordingMimeType || "audio/webm";

        mediaRecorder.ondataavailable = function (e) {
          audioChunks.push(e.data);
        };
        mediaRecorder.onstop = function () {
          stream.getTracks().forEach(function (t) { t.stop(); });
          handleRecordingComplete();
        };
        mediaRecorder.start();
        isRecording = true;
        switchVoiceState("recording");
        startWaveformViz(stream);
        startRecTimer();
      })
      .catch(function (err) {
        if (err.name === "NotAllowedError") {
          showMicPermissionError();
        } else if (err.name === "NotFoundError") {
          showToast("마이크가 연결되어 있지 않습니다.");
        } else if (err.name === "NotReadableError") {
          showToast("마이크가 다른 앱에서 사용 중입니다.");
        } else {
          showToast("마이크를 사용할 수 없습니다.");
        }
      });
  }

  function stopRecording() {
    if (mediaRecorder && mediaRecorder.state === "recording") {
      mediaRecorder.stop();
    }
    isRecording = false;
    stopWaveformViz();
    stopRecTimer();
  }

  /* ────────────────────────────────────────────
     Recording complete → Whisper → Search
     ──────────────────────────────────────────── */
  function handleRecordingComplete() {
    switchVoiceState("processing");
    var blob = new Blob(audioChunks, { type: recordingMimeType });

    if (blob.size > MAX_BLOB_SIZE) {
      switchVoiceState("idle");
      appendAIMessage("녹음이 너무 깁니다. 60초 이내로 다시 시도해주세요.");
      return;
    }

    var ext = getMimeExtension(recordingMimeType);
    var formData = new FormData();
    formData.append("audio", blob, "voice." + ext);

    fetch("/candidates/voice/", {
      method: "POST",
      headers: { "X-CSRFToken": getCSRF() },
      body: formData,
    })
      .then(function (r) {
        if (!r.ok) {
          if (r.status === 401 || r.status === 403) throw new Error("auth");
          if (r.status === 429) return r.json().then(function (d) { throw { rateLimit: true, msg: d.error }; });
          return r.json().then(function (d) { throw { msg: d.error || "음성 인식에 실패했습니다." }; });
        }
        return r.json();
      })
      .then(function (data) {
        switchVoiceState("idle");
        if (data.error) {
          appendAIMessage(data.error);
          return;
        }
        var text = (data.text || "").trim();
        if (!text) {
          appendAIMessage("음성이 감지되지 않았습니다. 다시 말씀해주세요.");
          return;
        }
        if (isSearching) return;
        appendUserMessage(text, true);
        appendThinking();
        doSearch(text, "voice");
      })
      .catch(function (err) {
        switchVoiceState("idle");
        if (err && err.rateLimit) {
          appendAIMessage(err.msg || "요청이 너무 많습니다. 잠시 후 다시 시도해주세요.");
        } else if (err && err.message === "auth") {
          appendAIMessage("로그인이 필요합니다. 페이지를 새로고침해주세요.");
        } else if (err && err.msg) {
          appendAIMessage(err.msg);
        } else if (!navigator.onLine) {
          appendAIMessage("인터넷 연결을 확인해주세요.");
        } else {
          appendAIMessage("음성 인식에 실패했습니다. 텍스트로 입력해주세요.");
        }
      });
  }

  /* ────────────────────────────────────────────
     Search API
     ──────────────────────────────────────────── */
  function doSearch(text, inputType) {
    if (isSearching) return;
    isSearching = true;
    fetch("/candidates/search/", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": getCSRF() },
      body: JSON.stringify({ message: text, session_id: sessionId, input_type: inputType }),
    })
      .then(function (r) {
        if (!r.ok) {
          if (r.status === 401 || r.status === 403) throw new Error("auth");
          if (r.status === 429) return r.json().then(function (d) { throw { rateLimit: true, msg: d.error }; });
          throw new Error("server");
        }
        return r.json();
      })
      .then(function (data) {
        isSearching = false;
        removeThinking();
        if (data.error) { appendAIMessage(data.error); return; }
        sessionId = data.session_id;
        sessionStorage.setItem("synco_session_id", sessionId);
        searchPerformedSinceOpen = true;

        /* AI 응답 + 결과 안내 */
        var msg = data.ai_message || "";
        if (data.result_count > 0) {
          msg += "\n\n" + data.result_count + "명을 찾았습니다. 대화창을 닫으면 결과를 확인할 수 있어요.";
          appendAIMessage(msg);
          blinkMinimizeBtn();
        } else if (data.result_count === 0) {
          msg += "\n\n조건에 맞는 후보자가 없습니다. 조건을 바꿔서 다시 말씀해주세요.";
          appendAIMessage(msg);
        } else {
          appendAIMessage(msg);
        }

        /* 실제 조회가 성공한 경우에만 결과 상태를 화면에 반영 */
        if (window.location.pathname === "/candidates/") {
          updateStatusBar(text, data.result_count);
          refreshCandidateList();
        }
      })
      .catch(function (err) {
        isSearching = false;
        removeThinking();
        if (err && err.rateLimit) {
          appendAIMessage(err.msg || "요청이 너무 많습니다.");
        } else if (err && err.message === "auth") {
          appendAIMessage("로그인이 필요합니다. 페이지를 새로고침해주세요.");
        } else if (!navigator.onLine) {
          appendAIMessage("인터넷 연결을 확인해주세요.");
        } else {
          appendAIMessage("일시적 오류가 발생했습니다. 다시 시도해주세요.");
        }
      });
  }

  /* ────────────────────────────────────────────
     Voice state switching (idle / recording / processing)
     ──────────────────────────────────────────── */
  function switchVoiceState(state) {
    hide("voice-idle");
    hide("voice-recording");
    hide("voice-processing");
    hide("text-input-area");

    if (state === "idle") {
      show("voice-idle");
    } else if (state === "recording") {
      show("voice-recording");
    } else if (state === "processing") {
      show("voice-processing");
    }
  }

  /* ────────────────────────────────────────────
     Waveform visualization (Web Audio API)
     ──────────────────────────────────────────── */
  function startWaveformViz(stream) {
    try {
      audioContext = new (window.AudioContext || window.webkitAudioContext)();
      analyserNode = audioContext.createAnalyser();
      analyserNode.fftSize = 128;
      analyserNode.smoothingTimeConstant = 0.4;
      var source = audioContext.createMediaStreamSource(stream);
      source.connect(analyserNode);
      var dataArray = new Uint8Array(analyserNode.frequencyBinCount);
      var bars = document.querySelectorAll(".waveform-bar");
      var barCount = bars.length;

      var half = Math.ceil(barCount / 2);

      function update() {
        if (!isRecording) return;
        analyserNode.getByteFrequencyData(dataArray);

        /* Build symmetric waveform: center is tallest, edges are shortest */
        for (var i = 0; i < half; i++) {
          var idx = Math.floor((i / half) * (dataArray.length * 0.6));
          var val = dataArray[idx] / 255;
          val = Math.min(1, val + Math.random() * 0.05);
          var h = Math.max(4, Math.round(val * 32));
          /* Mirror: i from left, mirror from right */
          bars[half - 1 - i].style.height = h + "px";
          if (half - 1 + i < barCount) bars[half - 1 + i].style.height = h + "px";
        }
        vizRaf = requestAnimationFrame(update);
      }
      vizRaf = requestAnimationFrame(update);
    } catch (e) {
      /* Fallback: CSS pulse for each bar */
      document.querySelectorAll(".waveform-bar").forEach(function (bar, i) {
        bar.style.height = "16px";
        bar.style.animation = "pulse 0.6s ease-in-out " + (i * 30) + "ms infinite alternate";
      });
    }
  }

  function stopWaveformViz() {
    if (vizRaf) { cancelAnimationFrame(vizRaf); vizRaf = null; }
    if (audioContext) {
      audioContext.close().catch(function () {});
      audioContext = null;
      analyserNode = null;
    }
    /* Reset bars */
    var bars = document.querySelectorAll(".waveform-bar");
    bars.forEach(function (bar) {
      bar.style.height = "4px";
      bar.style.animation = "";
    });
  }

  /* ────────────────────────────────────────────
     Recording timer
     ──────────────────────────────────────────── */
  function startRecTimer() {
    recStartTime = Date.now();
    var el = document.getElementById("rec-timer");
    recTimerInterval = setInterval(function () {
      var elapsed = Math.floor((Date.now() - recStartTime) / 1000);
      if (el) {
        var m = String(Math.floor(elapsed / 60)).padStart(2, "0");
        var s = String(elapsed % 60).padStart(2, "0");
        el.textContent = m + ":" + s;
      }
      if (elapsed >= MAX_RECORDING_SECONDS) stopRecording();
    }, 1000);
  }

  function stopRecTimer() {
    if (recTimerInterval) { clearInterval(recTimerInterval); recTimerInterval = null; }
  }

  /* ────────────────────────────────────────────
     Chat message helpers
     ──────────────────────────────────────────── */
  function appendUserMessage(text, isVoice) {
    var container = document.getElementById("chat-messages");
    var div = document.createElement("div");
    div.className = "flex justify-end";
    div.innerHTML =
      '<div class="bg-ink3 text-white rounded-2xl rounded-tr-sm px-3 py-2 max-w-[80%]">' +
      '<p class="text-base">' + escapeHtml(text) +
      "</p></div>";
    container.appendChild(div);
    scrollChat();
  }

  function appendAIMessage(text) {
    var container = document.getElementById("chat-messages");
    var div = document.createElement("div");
    div.className = "flex gap-2";
    div.innerHTML =
      '<div class="bg-gray-100 rounded-2xl rounded-tl-sm px-3 py-2 max-w-[80%]">' +
      '<p class="text-base text-gray-900 whitespace-pre-line">' + escapeHtml(text) + "</p></div>";
    container.appendChild(div);
    scrollChat();
  }

  function appendThinking() {
    var container = document.getElementById("chat-messages");
    var div = document.createElement("div");
    div.id = "thinking-indicator";
    div.className = "flex gap-2";
    div.innerHTML =
      '<div class="bg-gray-100 rounded-2xl rounded-tl-sm px-3 py-2">' +
      '<p class="text-base text-gray-400">검색 중' +
      '<span class="inline-flex ml-1"><span class="animate-bounce" style="animation-delay:0ms">.</span>' +
      '<span class="animate-bounce" style="animation-delay:150ms">.</span>' +
      '<span class="animate-bounce" style="animation-delay:300ms">.</span></span></p></div>';
    container.appendChild(div);
    scrollChat();
  }

  function removeThinking() {
    var el = document.getElementById("thinking-indicator");
    if (el) el.remove();
  }

  function scrollChat() {
    var c = document.getElementById("chat-messages");
    if (c) c.scrollTop = c.scrollHeight;
  }

  /* ────────────────────────────────────────────
     Mic permission error
     ──────────────────────────────────────────── */
  function showMicPermissionError() {
    switchVoiceState("idle");
    var container = document.getElementById("chat-messages");
    var div = document.createElement("div");
    div.className = "flex gap-2";
    div.innerHTML =
      '<div class="bg-red-50 border border-red-200 rounded-2xl rounded-tl-sm px-3 py-2 max-w-[90%]">' +
      '<p class="text-base text-red-800 font-medium">마이크 권한이 필요합니다</p>' +
      '<p class="text-sm text-red-600 mt-1">주소창 🔒 아이콘 → 마이크 → 허용으로 변경해주세요.</p>' +
      '<p class="text-sm text-gray-500 mt-1">또는 <button onclick="showTextInput()" class="text-ink3 underline">텍스트로 검색</button>할 수 있습니다.</p>' +
      "</div>";
    container.appendChild(div);
    scrollChat();
  }

  /* ────────────────────────────────────────────
     Chat history
     ──────────────────────────────────────────── */
  function loadChatHistory(sid) {
    var container = document.getElementById("chat-messages");
    if (container.dataset.historyLoaded === sid) return;
    fetch("/candidates/chat-history/?session_id=" + encodeURIComponent(sid))
      .then(function (r) { if (!r.ok) throw new Error(); return r.text(); })
      .then(function (html) {
        if (html.trim()) {
          container.innerHTML = html;
          container.dataset.historyLoaded = sid;
          scrollChat();
        }
      })
      .catch(function () {});
  }

  function refreshCandidateList() {
    var target = document.getElementById("search-area");
    if (!target) return;
    var url = "/candidates/";
    if (sessionId) url += "?session_id=" + sessionId;
    if (typeof htmx !== "undefined") {
      htmx.ajax("GET", url, { target: "#search-area", swap: "innerHTML" });
    }
  }

  function updateStatusBar(query, count) {
    var bar = document.getElementById("search-status-bar");
    if (bar) {
      bar.innerHTML =
        '<div class="px-4 py-2 bg-line border-b border-ink3/10 cursor-pointer" onclick="toggleChatbot()">' +
        '<p class="text-sm text-ink3 font-medium truncate">\uD83D\uDD0D "' +
        escapeHtml(query) + '" \u2014 ' + count + '\uBA85 \uCC3E\uC74C</p></div>';
    }
  }

  /* ────────────────────────────────────────────
     Drag to close (mobile)
     ──────────────────────────────────────────── */
  (function initDrag() {
    var handle = document.getElementById("drag-handle");
    if (!handle) return;
    var startY = 0;
    handle.addEventListener("touchstart", function (e) { startY = e.touches[0].clientY; }, { passive: true });
    handle.addEventListener("touchend", function (e) {
      var dy = e.changedTouches[0].clientY - startY;
      if (dy > 80) toggleChatbot();
    });
  })();

  /* ────────────────────────────────────────────
     First-visit tooltip
     ──────────────────────────────────────────── */
  (function initTooltip() {
    if (localStorage.getItem("synco_fab_seen")) return;
    var tip = document.getElementById("fab-tooltip");
    if (tip) {
      tip.classList.remove("hidden");
      setTimeout(function () { tip.classList.add("hidden"); }, 6000);
      localStorage.setItem("synco_fab_seen", "1");
    }
  })();


  /* ────────────────────────────────────────────
     Utilities
     ──────────────────────────────────────────── */
  function detectMimeType() {
    var types = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus", "audio/ogg"];
    for (var i = 0; i < types.length; i++) {
      if (typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(types[i])) return types[i];
    }
    return "";
  }

  function getMimeExtension(mime) {
    if (mime.indexOf("mp4") !== -1) return "mp4";
    if (mime.indexOf("ogg") !== -1) return "ogg";
    return "webm";
  }

  function getCSRF() {
    var m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : "";
  }

  function escapeHtml(text) {
    var d = document.createElement("div");
    d.textContent = text;
    return d.innerHTML;
  }

  function show(id) { var el = document.getElementById(id); if (el) el.classList.remove("hidden"); }
  function hide(id) { var el = document.getElementById(id); if (el) el.classList.add("hidden"); }

  function blinkMinimizeBtn() {
    var btn = document.getElementById("minimize-btn");
    if (!btn) return;
    /* voice-idle가 hidden이면 표시 전환 */
    show("voice-idle");
    hide("voice-recording");
    hide("voice-processing");
    hide("text-input-area");
    btn.classList.remove("text-gray-400");
    btn.classList.add("text-red-500", "animate-pulse-hint");
  }

  function stopMinimizeBlink() {
    var btn = document.getElementById("minimize-btn");
    if (!btn) return;
    btn.classList.remove("text-red-500", "animate-pulse-hint");
    btn.classList.add("text-gray-400");
  }

  function showToast(msg) {
    if (typeof window.showToast === "function") {
      window.showToast(msg);
    } else {
      alert(msg);
    }
  }
})();
