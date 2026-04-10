// static/js/context-autosave.js
// Three-tier autosave: periodic (primary) + fetch+keepalive (unload) + HTMX event (in-app nav)

(function () {
  "use strict";

  const AUTOSAVE_INTERVAL_MS = 30000; // 30 seconds
  let _timer = null;
  let _dirty = false;
  let _lastSaved = null;

  function getAutosaveForms() {
    return document.querySelectorAll("form[data-autosave]");
  }

  function getProjectPk() {
    var el = document.querySelector("[data-project-pk]");
    return el ? el.dataset.projectPk : null;
  }

  function getFormName() {
    var form = document.querySelector("form[data-autosave]");
    return form ? form.dataset.autosave : null;
  }

  function collectFormData(form) {
    var formData = new FormData(form);
    var fields = {};
    for (var pair of formData.entries()) {
      if (pair[0] === "csrfmiddlewaretoken") continue;
      fields[pair[0]] = pair[1];
    }
    return fields;
  }

  function buildPayload() {
    var form = document.querySelector("form[data-autosave]");
    if (!form) return null;
    var formName = getFormName();
    var fields = collectFormData(form);
    return {
      last_step: formName,
      pending_action: form.dataset.autosaveAction || "",
      draft_data: {
        form: formName,
        fields: fields,
      },
    };
  }

  function getSaveUrl() {
    var pk = getProjectPk();
    if (!pk) return null;
    return "/projects/" + pk + "/context/save/";
  }

  function getCsrfToken() {
    var cookie = document.cookie
      .split("; ")
      .find(function (c) { return c.startsWith("csrftoken="); });
    return cookie ? cookie.split("=")[1] : "";
  }

  // Tier 1: Periodic save via fetch
  function periodicSave() {
    if (!_dirty) return;
    var url = getSaveUrl();
    var payload = buildPayload();
    if (!url || !payload) return;

    fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
      },
      body: JSON.stringify(payload),
    })
      .then(function () {
        _dirty = false;
        _lastSaved = Date.now();
      })
      .catch(function () {
        /* silent fail — will retry next interval */
      });
  }

  // Tier 2: fetch with keepalive on unload (replaces sendBeacon)
  function keepaliveSave() {
    if (!_dirty) return;
    var url = getSaveUrl();
    var payload = buildPayload();
    if (!url || !payload) return;

    fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
      },
      body: JSON.stringify(payload),
      keepalive: true,
    }).catch(function () {
      /* silent — page is unloading */
    });
  }

  // Tier 3: HTMX in-app navigation
  function htmxSave() {
    if (!_dirty) return;
    periodicSave();
  }

  function markDirty() {
    _dirty = true;
  }

  function init() {
    var forms = getAutosaveForms();
    if (forms.length === 0) return;

    // Listen for input changes
    forms.forEach(function (form) {
      form.addEventListener("input", markDirty);
      form.addEventListener("change", markDirty);
    });

    // Tier 1: periodic
    _timer = setInterval(periodicSave, AUTOSAVE_INTERVAL_MS);

    // Tier 2: unload (A7: fetch+keepalive instead of sendBeacon)
    window.addEventListener("beforeunload", keepaliveSave);

    // Tier 3: HTMX navigation
    document.addEventListener("htmx:beforeHistorySave", htmxSave);
  }

  function cleanup() {
    if (_timer) {
      clearInterval(_timer);
      _timer = null;
    }
    window.removeEventListener("beforeunload", keepaliveSave);
    document.removeEventListener("htmx:beforeHistorySave", htmxSave);
  }

  // Re-initialize after HTMX swaps
  document.addEventListener("htmx:afterSettle", function () {
    cleanup();
    init();
  });

  // Initial setup
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
