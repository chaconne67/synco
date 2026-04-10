const API = {
  async getServerUrl() {
    const { serverUrl } = await chrome.storage.sync.get("serverUrl");
    return serverUrl || "https://synco.example.com";
  },

  async request(path, options = {}) {
    const baseUrl = await this.getServerUrl();
    const url = `${baseUrl}/candidates/extension${path}`;

    const defaultHeaders = { "Content-Type": "application/json" };
    const headers = { ...defaultHeaders, ...(options.headers || {}) };

    const response = await fetch(url, {
      credentials: "include",
      ...options,
      headers,
    });
    return response.json();
  },

  async checkAuth() {
    try {
      return await this.request("/auth-status/");
    } catch (e) {
      return { status: "error", errors: [e.message] };
    }
  },

  async saveProfile(data) {
    return this.request("/save-profile/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async checkDuplicate(data) {
    return this.request("/check-duplicate/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async search(query, page = 1) {
    return this.request(`/search/?q=${encodeURIComponent(query)}&page=${page}`);
  },

  async getStats() {
    return this.request("/stats/");
  },
};

// Message routing
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    try {
      switch (message.type) {
        case "CHECK_AUTH":
          sendResponse(await API.checkAuth());
          break;
        case "CHECK_DUPLICATE":
          sendResponse(await API.checkDuplicate(message.data));
          break;
        case "SAVE_PROFILE":
          sendResponse(await API.saveProfile(message.data));
          break;
        case "SEARCH":
          sendResponse(await API.search(message.query, message.page));
          break;
        case "GET_STATS":
          sendResponse(await API.getStats());
          break;
        default:
          sendResponse({ status: "error", errors: ["Unknown message type"] });
      }
    } catch (e) {
      sendResponse({ status: "error", errors: [e.message] });
    }
  })();
  return true; // keep message channel open for async response
});

chrome.runtime.onInstalled.addListener(() => API.checkAuth());
