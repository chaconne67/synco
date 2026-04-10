const SyncoOverlay = {
  _host: null,
  _shadow: null,

  create() {
    if (this._host) this.remove();

    this._host = document.createElement("div");
    this._host.id = "synco-overlay-host";
    this._shadow = this._host.attachShadow({ mode: "closed" });

    // Load overlay CSS into shadow DOM
    const style = document.createElement("link");
    style.rel = "stylesheet";
    style.href = chrome.runtime.getURL("styles/overlay.css");
    this._shadow.appendChild(style);

    const container = document.createElement("div");
    container.className = "synco-overlay";
    container.innerHTML = `
      <div class="synco-header">
        <span class="synco-logo">Synco</span>
        <button class="synco-close" title="닫기">&times;</button>
      </div>
      <div class="synco-body">
        <div class="synco-status">확인 중...</div>
        <div class="synco-actions" style="display:none;"></div>
        <div class="synco-result" style="display:none;"></div>
      </div>
    `;
    this._shadow.appendChild(container);

    // Close button
    container.querySelector(".synco-close").addEventListener("click", () => this.remove());

    document.body.appendChild(this._host);
    return this._shadow;
  },

  remove() {
    if (this._host) {
      this._host.remove();
      this._host = null;
      this._shadow = null;
    }
  },

  getElement(selector) {
    return this._shadow?.querySelector(selector);
  },

  setStatus(text, type = "info") {
    const el = this.getElement(".synco-status");
    if (el) {
      el.textContent = text;
      el.className = `synco-status synco-status-${type}`;
    }
  },

  showActions(html) {
    const el = this.getElement(".synco-actions");
    if (el) {
      el.innerHTML = html;
      el.style.display = "block";
    }
  },

  showResult(html) {
    const el = this.getElement(".synco-result");
    if (el) {
      el.innerHTML = html;
      el.style.display = "block";
    }
  },

  addActionListener(selector, handler) {
    const el = this.getElement(selector);
    if (el) el.addEventListener("click", handler);
  },
};
