/**
 * VoiceAgent — MediaRecorder-based voice agent with conversation UI and confirm flow.
 *
 * Endpoints:
 *   POST /voice/transcribe/  — audio → text
 *   POST /voice/intent/      — text → intent + entities
 *   POST /voice/preview/     — intent → preview (URL, summary, etc.)
 *   POST /voice/confirm/     — confirmed intent → execute action
 *   POST /voice/reset/       — clear server-side session (Amendment A4)
 *   GET  /voice/meeting-upload/ — meeting upload panel HTML
 *
 * Amendments:
 *   A4  — close() calls POST /voice/reset/ instead of /voice/history/
 *   A10 — show_meeting_panel handling in _executeImmediate
 */
(function () {
  "use strict";

  var INACTIVITY_TIMEOUT = 60000; // 1 minute

  window.VoiceAgent = {
    modal: null,
    messages: null,
    textInput: null,
    micBtn: null,
    recording: false,
    mediaRecorder: null,
    audioChunks: [],
    _inactivityTimer: null,

    // ── Initialization ──────────────────────────────────────────

    _init: function () {
      this.modal = document.getElementById("voice-modal");
      this.messages = document.getElementById("voice-messages");
      this.textInput = document.getElementById("voice-text-input");
      this.micBtn = document.getElementById("voice-mic-btn");
    },

    _ensureInit: function () {
      if (!this.modal) this._init();
    },

    // ── Toggle / Open / Close ───────────────────────────────────

    toggle: function () {
      this._ensureInit();
      if (!this.modal) return;
      if (this.modal.classList.contains("hidden")) {
        this.open();
      } else {
        this.close();
      }
    },

    open: function () {
      this._ensureInit();
      if (!this.modal) return;
      this.modal.classList.remove("hidden");
      if (this.textInput) this.textInput.focus();
      this._resetInactivityTimer();
    },

    close: function () {
      if (!this.modal) return;
      this.modal.classList.add("hidden");
      if (this.recording) this.stopRecording();
      this._clearInactivityTimer();
      // Amendment A4: reset server-side session on close
      this._post("/voice/reset/", {}).catch(function () {});
    },

    // ── Inactivity Timer ────────────────────────────────────────

    _resetInactivityTimer: function () {
      this._clearInactivityTimer();
      var self = this;
      this._inactivityTimer = setTimeout(function () {
        self._addMessage("system", "비활성 상태로 세션을 종료합니다.");
        setTimeout(function () {
          self.close();
        }, 1500);
      }, INACTIVITY_TIMEOUT);
    },

    _clearInactivityTimer: function () {
      if (this._inactivityTimer) {
        clearTimeout(this._inactivityTimer);
        this._inactivityTimer = null;
      }
    },

    // ── Text Input ──────────────────────────────────────────────

    sendText: function () {
      this._ensureInit();
      if (!this.textInput) return;
      var text = this.textInput.value.trim();
      if (!text) return;
      this.textInput.value = "";
      this._resetInactivityTimer();
      this._processText(text);
    },

    // ── Recording ───────────────────────────────────────────────

    toggleRecording: function () {
      if (this.recording) {
        this.stopRecording();
      } else {
        this.startRecording();
      }
    },

    startRecording: function () {
      var self = this;
      this._ensureInit();
      if (this.recording) return;

      navigator.mediaDevices
        .getUserMedia({ audio: true })
        .then(function (stream) {
          self.audioChunks = [];
          self.mediaRecorder = new MediaRecorder(stream, {
            mimeType: self._getSupportedMimeType(),
          });

          self.mediaRecorder.addEventListener("dataavailable", function (e) {
            if (e.data.size > 0) self.audioChunks.push(e.data);
          });

          self.mediaRecorder.addEventListener("stop", function () {
            stream.getTracks().forEach(function (t) {
              t.stop();
            });
            self._onRecordingStop();
          });

          self.mediaRecorder.start();
          self.recording = true;
          self._setMicActive(true);
          self._addMessage("system", "녹음 중...");
          self._resetInactivityTimer();
        })
        .catch(function (err) {
          console.error("Microphone access denied:", err);
          self._addMessage("system", "마이크 접근이 거부되었습니다.");
        });
    },

    stopRecording: function () {
      if (!this.recording || !this.mediaRecorder) return;
      this.mediaRecorder.stop();
      this.recording = false;
      this._setMicActive(false);
    },

    _onRecordingStop: function () {
      if (this.audioChunks.length === 0) return;
      var blob = new Blob(this.audioChunks, { type: "audio/webm" });
      this.audioChunks = [];
      this._transcribeAudio(blob);
    },

    _getSupportedMimeType: function () {
      var types = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
      for (var i = 0; i < types.length; i++) {
        if (MediaRecorder.isTypeSupported(types[i])) return types[i];
      }
      return "audio/webm";
    },

    _setMicActive: function (active) {
      if (!this.micBtn) return;
      if (active) {
        this.micBtn.classList.remove(
          "bg-gray-100",
          "text-gray-600",
          "hover:bg-indigo-100",
          "hover:text-indigo-600"
        );
        this.micBtn.classList.add("bg-red-500", "text-white", "hover:bg-red-600");
      } else {
        this.micBtn.classList.remove("bg-red-500", "text-white", "hover:bg-red-600");
        this.micBtn.classList.add(
          "bg-gray-100",
          "text-gray-600",
          "hover:bg-indigo-100",
          "hover:text-indigo-600"
        );
      }
    },

    // ── Transcription ───────────────────────────────────────────

    _transcribeAudio: function (blob) {
      var self = this;
      var formData = new FormData();
      formData.append("audio", blob, "recording.webm");

      fetch("/voice/transcribe/", {
        method: "POST",
        headers: { "X-CSRFToken": this._getCsrf() },
        body: formData,
      })
        .then(function (r) {
          return r.json();
        })
        .then(function (data) {
          if (data.text) {
            self._removeLastSystemMessage("녹음 중...");
            self._processText(data.text);
          } else {
            self._addMessage("system", "음성을 인식하지 못했습니다. 다시 시도해주세요.");
          }
        })
        .catch(function () {
          self._addMessage("system", "전사 중 오류가 발생했습니다.");
        });
    },

    // ── Intent Pipeline ─────────────────────────────────────────

    _processText: function (text) {
      var self = this;
      this._addMessage("user", text);
      this._addMessage("system", "처리 중...");

      this._post("/voice/intent/", { text: text })
        .then(function (data) {
          self._removeLastSystemMessage("처리 중...");
          if (data.intent && data.intent !== "unknown") {
            if (data.immediate) {
              self._executeImmediate(data);
            } else {
              self._showPreview(data);
            }
          } else {
            self._addMessage(
              "assistant",
              data.response || "죄송합니다, 요청을 이해하지 못했습니다."
            );
          }
        })
        .catch(function () {
          self._removeLastSystemMessage("처리 중...");
          self._addMessage("system", "요청 처리 중 오류가 발생했습니다.");
        });
    },

    // ── Immediate Execution (Amendment A10) ─────────────────────

    _executeImmediate: function (intentData) {
      var self = this;
      var context = this._getContext();
      this._post("/voice/preview/", {
        intent: intentData.intent,
        entities: intentData.entities,
        project_id: context.project_id || "",
      })
        .then(function (data) {
          // Amendment A10: show_meeting_panel handling
          if (data.action === "show_meeting_panel") {
            self._showMeetingPanel();
            return;
          }
          if (data.url) {
            self._addMessage("assistant", data.summary);
            setTimeout(function () {
              window.location.href = data.url;
            }, 500);
          } else if (data.candidates) {
            // search_candidate results shown inline
            self._showSearchResults(data);
          } else {
            self._addMessage("assistant", data.summary || "완료");
          }
        })
        .catch(function () {
          self._addMessage("system", "실행 중 오류가 발생했습니다.");
        });
    },

    // ── Preview & Confirm ───────────────────────────────────────

    _showPreview: function (intentData) {
      var self = this;
      var context = this._getContext();

      this._post("/voice/preview/", {
        intent: intentData.intent,
        entities: intentData.entities,
        project_id: context.project_id || "",
      })
        .then(function (data) {
          if (data.action === "show_meeting_panel") {
            self._showMeetingPanel();
            return;
          }
          self._addMessage("assistant", data.summary || "다음 작업을 수행할까요?");
          self._addConfirmButtons(intentData);
        })
        .catch(function () {
          self._addMessage("system", "미리보기 오류가 발생했습니다.");
        });
    },

    _addConfirmButtons: function (intentData) {
      var self = this;
      var wrapper = document.createElement("div");
      wrapper.className = "flex gap-2 mt-1";

      var confirmBtn = document.createElement("button");
      confirmBtn.className =
        "rounded-lg bg-indigo-600 px-4 py-1.5 text-sm text-white hover:bg-indigo-700 transition-colors";
      confirmBtn.textContent = "확인";
      confirmBtn.onclick = function () {
        wrapper.remove();
        self._confirmAction(intentData);
      };

      var cancelBtn = document.createElement("button");
      cancelBtn.className =
        "rounded-lg border border-gray-300 px-4 py-1.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors";
      cancelBtn.textContent = "취소";
      cancelBtn.onclick = function () {
        wrapper.remove();
        self._addMessage("assistant", "취소되었습니다.");
      };

      wrapper.appendChild(confirmBtn);
      wrapper.appendChild(cancelBtn);
      this.messages.appendChild(wrapper);
      this.messages.scrollTop = this.messages.scrollHeight;
    },

    _confirmAction: function (intentData) {
      var self = this;
      var context = this._getContext();

      this._post("/voice/confirm/", {
        intent: intentData.intent,
        entities: intentData.entities,
        project_id: context.project_id || "",
      })
        .then(function (data) {
          if (data.url) {
            self._addMessage("assistant", data.summary || "완료되었습니다.");
            setTimeout(function () {
              window.location.href = data.url;
            }, 500);
          } else {
            self._addMessage("assistant", data.summary || "완료되었습니다.");
          }
        })
        .catch(function () {
          self._addMessage("system", "실행 중 오류가 발생했습니다.");
        });
    },

    // ── Meeting Panel (Amendment A10) ───────────────────────────

    _showMeetingPanel: function () {
      var self = this;
      fetch("/voice/meeting-upload/", {
        method: "GET",
        headers: { "X-CSRFToken": this._getCsrf() },
      })
        .then(function (r) {
          return r.json();
        })
        .then(function (data) {
          self.messages.innerHTML = data.html;
        })
        .catch(function () {
          self._addMessage("system", "미팅 패널을 불러오지 못했습니다.");
        });
    },

    // ── Search Results ──────────────────────────────────────────

    _showSearchResults: function (data) {
      this._addMessage("assistant", data.summary);
      if (data.candidates && data.candidates.length > 0) {
        var list = document.createElement("div");
        list.className = "space-y-1 mt-1";
        data.candidates.forEach(function (c) {
          var div = document.createElement("div");
          div.className = "rounded-lg border px-3 py-2 text-sm";
          div.textContent = c.name;
          list.appendChild(div);
        });
        this.messages.appendChild(list);
        this.messages.scrollTop = this.messages.scrollHeight;
      }
    },

    // ── Message Rendering ───────────────────────────────────────

    _addMessage: function (role, text) {
      if (!this.messages) return;
      var div = document.createElement("div");
      div.className = "text-sm";

      if (role === "user") {
        div.className += " text-right";
        var bubble = document.createElement("span");
        bubble.className =
          "inline-block rounded-2xl bg-indigo-600 px-3 py-2 text-white max-w-[80%] text-left";
        bubble.textContent = text;
        div.appendChild(bubble);
      } else if (role === "assistant") {
        var bubble = document.createElement("span");
        bubble.className =
          "inline-block rounded-2xl bg-gray-100 px-3 py-2 text-gray-900 max-w-[80%]";
        bubble.textContent = text;
        div.appendChild(bubble);
      } else {
        // system
        div.className += " text-gray-500 text-center text-xs";
        div.textContent = text;
      }

      this.messages.appendChild(div);
      this.messages.scrollTop = this.messages.scrollHeight;
    },

    _removeLastSystemMessage: function (text) {
      if (!this.messages) return;
      var children = this.messages.children;
      for (var i = children.length - 1; i >= 0; i--) {
        if (
          children[i].classList.contains("text-center") &&
          children[i].textContent === text
        ) {
          children[i].remove();
          break;
        }
      }
    },

    // ── Context ─────────────────────────────────────────────────

    _getContext: function () {
      var fab = document.getElementById("voice-agent-fab");
      if (!fab) return {};
      try {
        return JSON.parse(fab.dataset.voiceContext || "{}");
      } catch (e) {
        return {};
      }
    },

    // ── HTTP Helpers ────────────────────────────────────────────

    _post: function (url, data) {
      return fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": this._getCsrf(),
        },
        body: JSON.stringify(data),
      }).then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      });
    },

    _getCsrf: function () {
      var meta = document.querySelector('meta[name="csrf-token"]');
      if (meta) return meta.getAttribute("content");
      // Fallback: read from cookie
      var match = document.cookie.match(/csrftoken=([^;]+)/);
      return match ? match[1] : "";
    },
  };
})();
