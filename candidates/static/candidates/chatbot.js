/* synco chatbot — voice + text search */
(function () {
  "use strict";

  var sessionId = sessionStorage.getItem("synco_session_id") || null;
  var mediaRecorder = null;
  var audioChunks = [];
  var isRecording = false;

  window.toggleChatbot = function () {
    var modal = document.getElementById("chatbot-modal");
    var overlay = document.getElementById("chatbot-overlay");
    var toggle = document.getElementById("chatbot-toggle");
    var isOpen = !modal.classList.contains("hidden");

    if (isOpen) {
      modal.classList.add("hidden");
      overlay.classList.add("hidden");
      toggle.classList.remove("hidden");
      refreshCandidateList();
    } else {
      modal.classList.remove("hidden");
      overlay.classList.remove("hidden");
      toggle.classList.add("hidden");
      document.getElementById("chat-input").focus();
      scrollChat();
    }
  };

  window.sendMessage = function () {
    var input = document.getElementById("chat-input");
    var text = input.value.trim();
    if (!text) return;
    input.value = "";
    appendUserMessage(text);
    appendThinking();
    doSearch(text, "text");
  };

  window.toggleRecording = function () {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  function startRecording() {
    navigator.mediaDevices
      .getUserMedia({ audio: true })
      .then(function (stream) {
        audioChunks = [];
        mediaRecorder = new MediaRecorder(stream);
        mediaRecorder.ondataavailable = function (e) {
          audioChunks.push(e.data);
        };
        mediaRecorder.onstop = function () {
          stream.getTracks().forEach(function (t) { t.stop(); });
          handleRecordingComplete();
        };
        mediaRecorder.start();
        isRecording = true;
        setMicState("recording");
      })
      .catch(function () {
        showToast("마이크 권한을 허용해주세요");
      });
  }

  function stopRecording() {
    if (mediaRecorder && mediaRecorder.state === "recording") {
      mediaRecorder.stop();
    }
    isRecording = false;
  }

  function handleRecordingComplete() {
    setMicState("processing");
    var blob = new Blob(audioChunks, { type: "audio/webm" });
    var formData = new FormData();
    formData.append("audio", blob, "voice.webm");

    fetch("/candidates/voice/", {
      method: "POST",
      headers: { "X-CSRFToken": getCSRF() },
      body: formData,
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        setMicState("idle");
        if (data.error) {
          showToast(data.error);
          return;
        }
        appendUserMessage(data.text, true);
        appendThinking();
        doSearch(data.text, "voice");
      })
      .catch(function () {
        setMicState("idle");
        showToast("음성 인식에 실패했습니다. 텍스트로 입력해주세요.");
      });
  }

  function doSearch(text, inputType) {
    fetch("/candidates/search/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCSRF(),
      },
      body: JSON.stringify({
        message: text,
        session_id: sessionId,
        input_type: inputType,
      }),
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        removeThinking();
        if (data.error) {
          appendAIMessage(data.error);
          return;
        }
        sessionId = data.session_id;
        sessionStorage.setItem("synco_session_id", sessionId);
        appendAIMessage(data.ai_message);
        updateStatusBar(text, data.result_count);
      })
      .catch(function () {
        removeThinking();
        appendAIMessage("검색 중 오류가 발생했습니다.");
      });
  }

  function appendUserMessage(text, isVoice) {
    var container = document.getElementById("chat-messages");
    var div = document.createElement("div");
    div.className = "flex justify-end";
    div.innerHTML =
      '<div class="bg-primary text-white rounded-2xl rounded-tr-sm px-3 py-2 max-w-[80%]">' +
      '<p class="text-[14px]">' + escapeHtml(text) +
      (isVoice ? ' <span class="text-[11px] opacity-70">🎤</span>' : "") +
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
      '<p class="text-[14px] text-gray-900">' + escapeHtml(text) + "</p></div>";
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
      '<p class="text-[14px] text-gray-400">생각 중' +
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
    var container = document.getElementById("chat-messages");
    container.scrollTop = container.scrollHeight;
  }

  function setMicState(state) {
    var btn = document.getElementById("mic-btn");
    var icon = document.getElementById("mic-icon");
    var recIcon = document.getElementById("mic-recording-icon");
    var spinner = document.getElementById("mic-spinner");

    icon.classList.add("hidden");
    recIcon.classList.add("hidden");
    spinner.classList.add("hidden");

    if (state === "idle") {
      btn.className = btn.className.replace(/bg-red-500|bg-gray-400/g, "bg-primary");
      icon.classList.remove("hidden");
    } else if (state === "recording") {
      btn.className = btn.className.replace(/bg-primary|bg-gray-400/g, "bg-red-500");
      recIcon.classList.remove("hidden");
    } else if (state === "processing") {
      btn.className = btn.className.replace(/bg-primary|bg-red-500/g, "bg-gray-400");
      spinner.classList.remove("hidden");
    }
  }

  function refreshCandidateList() {
    var url = "/candidates/";
    if (sessionId) url += "?session_id=" + sessionId;
    htmx.ajax("GET", url, { target: "#candidate-list", swap: "innerHTML" });
  }

  function updateStatusBar(query, count) {
    var bar = document.getElementById("search-status-bar");
    if (bar) {
      bar.innerHTML =
        '<div class="px-4 py-2 bg-primary-light border-b border-primary/10 cursor-pointer" onclick="toggleChatbot()">' +
        '<p class="text-[13px] text-primary font-medium truncate">🔍 "' +
        escapeHtml(query) + '" — ' + count + "명 찾음</p></div>";
    }
  }

  function showToast(msg) {
    var container = document.getElementById("toast-container");
    if (!container) return;
    var div = document.createElement("div");
    div.className = "bg-gray-800 text-white text-[13px] px-4 py-2 rounded-lg shadow-lg";
    div.textContent = msg;
    container.appendChild(div);
    setTimeout(function () { div.remove(); }, 3000);
  }

  function getCSRF() {
    var cookie = document.cookie.match(/csrftoken=([^;]+)/);
    return cookie ? cookie[1] : "";
  }

  function escapeHtml(text) {
    var div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      var modal = document.getElementById("chatbot-modal");
      if (modal && !modal.classList.contains("hidden")) {
        toggleChatbot();
      }
    }
  });
})();
