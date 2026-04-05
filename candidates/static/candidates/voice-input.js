(function () {
  "use strict";

  var SpeechRecognition =
    window.SpeechRecognition || window.webkitSpeechRecognition;

  function initVoiceInput() {
    var btns = document.querySelectorAll("[data-voice-input]");
    btns.forEach(function (btn) {
      if (btn.dataset.voiceInitialized) return;
      btn.dataset.voiceInitialized = "true";

      if (!SpeechRecognition) {
        btn.style.display = "none";
        return;
      }

      var recognition = new SpeechRecognition();
      recognition.lang = "ko-KR";
      recognition.continuous = true;
      recognition.interimResults = true;

      var isRecording = false;
      var textarea = btn.closest("form").querySelector("textarea[name='content']");
      var methodInput = btn.closest("form").querySelector("input[name='input_method']");

      recognition.onresult = function (e) {
        var transcript = "";
        for (var i = e.resultIndex; i < e.results.length; i++) {
          transcript += e.results[i][0].transcript;
        }
        if (textarea) {
          // Append transcript to existing content
          var existing = textarea.value;
          if (existing && !existing.endsWith(" ") && !existing.endsWith("\n")) {
            existing += " ";
          }
          textarea.value = existing + transcript;
        }
        if (methodInput) {
          methodInput.value = "voice";
        }
      };

      recognition.onerror = function () {
        isRecording = false;
        btn.classList.remove("text-red-500");
        btn.classList.add("text-gray-400");
      };

      recognition.onend = function () {
        isRecording = false;
        btn.classList.remove("text-red-500");
        btn.classList.add("text-gray-400");
      };

      btn.addEventListener("click", function (e) {
        e.preventDefault();
        if (isRecording) {
          recognition.stop();
        } else {
          recognition.start();
          isRecording = true;
          btn.classList.remove("text-gray-400");
          btn.classList.add("text-red-500");
        }
      });
    });
  }

  // Initial load
  initVoiceInput();

  // Re-initialize after HTMX partial swap
  document.addEventListener("htmx:afterSettle", initVoiceInput);
})();
