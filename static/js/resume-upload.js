/**
 * P18: Resume upload — drag & drop + file input handling.
 * Posts files to /upload/, extracts batch_id, posts /process/,
 * then starts HTMX polling on /status/.
 */
(function () {
  "use strict";

  function init() {
    const dropZone = document.getElementById("drop-zone");
    const fileInput = document.getElementById("resume-file-input");
    if (!dropZone || !fileInput) return;

    const uploadUrl = dropZone.dataset.uploadUrl;
    const processUrl = dropZone.dataset.processUrl;
    const statusUrl = dropZone.dataset.statusUrl;
    const csrfToken = document.querySelector("[name=csrfmiddlewaretoken]")?.value
      || document.querySelector("body")?.getAttribute("hx-headers")
        && JSON.parse(document.querySelector("body").getAttribute("hx-headers"))["X-CSRFToken"]
      || "";

    // Click to open file dialog
    dropZone.addEventListener("click", function () {
      fileInput.click();
    });

    // File input change
    fileInput.addEventListener("change", function () {
      if (fileInput.files.length > 0) {
        handleFiles(fileInput.files);
        fileInput.value = "";
      }
    });

    // Drag & drop events
    dropZone.addEventListener("dragover", function (e) {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.add("border-primary", "bg-primary/5");
    });

    dropZone.addEventListener("dragleave", function (e) {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.remove("border-primary", "bg-primary/5");
    });

    dropZone.addEventListener("drop", function (e) {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.remove("border-primary", "bg-primary/5");
      if (e.dataTransfer.files.length > 0) {
        handleFiles(e.dataTransfer.files);
      }
    });

    function handleFiles(files) {
      const formData = new FormData();
      for (let i = 0; i < files.length; i++) {
        formData.append("files", files[i]);
      }

      // Show loading state
      const container = document.getElementById("resume-status-container");
      if (container) {
        container.innerHTML =
          '<div class="flex items-center gap-2 p-3 bg-white rounded-lg border border-gray-100">' +
          '<svg class="animate-spin w-5 h-5 text-primary" fill="none" viewBox="0 0 24 24">' +
          '<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>' +
          '<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"/>' +
          '</svg>' +
          '<span class="text-[13px] text-gray-500">업로드 중...</span>' +
          '</div>';
      }

      // Step 1: Upload files
      fetch(uploadUrl, {
        method: "POST",
        headers: { "X-CSRFToken": csrfToken },
        body: formData,
      })
        .then(function (resp) {
          if (!resp.ok) throw new Error("Upload failed");
          return resp.text();
        })
        .then(function (html) {
          if (container) {
            container.innerHTML = html;
            htmx.process(container);
          }

          // Extract batch_id from response
          var statusList = container.querySelector("#resume-status-list");
          var batchId = statusList ? statusList.dataset.batchId : null;

          if (batchId) {
            // Step 2: Trigger processing
            var processForm = new FormData();
            processForm.append("batch_id", batchId);
            fetch(processUrl, {
              method: "POST",
              headers: { "X-CSRFToken": csrfToken },
              body: processForm,
            })
              .then(function (resp) {
                if (!resp.ok) throw new Error("Process failed");
                return resp.text();
              })
              .then(function (html) {
                if (container) {
                  container.innerHTML = html;
                  htmx.process(container);
                }
                // Start polling for updates
                startPolling(statusUrl, batchId, container, csrfToken);
              })
              .catch(function (err) {
                console.error("Process error:", err);
              });
          }
        })
        .catch(function (err) {
          console.error("Upload error:", err);
          if (container) {
            container.innerHTML =
              '<div class="p-3 bg-red-50 rounded-lg border border-red-100 text-[13px] text-red-600">' +
              '업로드에 실패했습니다. 다시 시도해주세요.</div>';
          }
        });
    }
  }

  function startPolling(statusUrl, batchId, container, csrfToken) {
    var pollInterval = setInterval(function () {
      var url = statusUrl + "?batch=" + encodeURIComponent(batchId);
      fetch(url, {
        method: "GET",
        headers: {
          "X-CSRFToken": csrfToken,
          "HX-Request": "true",
        },
      })
        .then(function (resp) {
          if (!resp.ok) throw new Error("Status check failed");
          return resp.text();
        })
        .then(function (html) {
          if (container) {
            container.innerHTML = html;
            htmx.process(container);
          }

          // Check if all uploads are in terminal state
          var activeItems = container.querySelectorAll(".animate-spin");
          if (activeItems.length === 0) {
            clearInterval(pollInterval);
          }
        })
        .catch(function (err) {
          console.error("Polling error:", err);
          clearInterval(pollInterval);
        });
    }, 2000);
  }

  // Initialize on DOMContentLoaded and after HTMX swaps
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
  document.addEventListener("htmx:afterSwap", function (e) {
    if (e.detail.target.id === "tab-content" || e.detail.target.id === "main-content") {
      init();
    }
  });
})();
