document.addEventListener("DOMContentLoaded", async () => {
  // Load today's save count
  const todayKey = `saves_${new Date().toISOString().slice(0, 10)}`;
  const counts = await chrome.storage.local.get(todayKey);
  document.getElementById("todaySaves").textContent = counts[todayKey] || 0;

  // Load total candidates from server
  const statsResult = await chrome.runtime.sendMessage({ type: "GET_STATS" });
  if (statsResult.status === "success") {
    document.getElementById("totalCandidates").textContent =
      statsResult.data.total_candidates.toLocaleString();
  }

  // Load recent saves
  const { recentSaves = [] } = await chrome.storage.local.get("recentSaves");
  const recentList = document.getElementById("recentList");
  if (recentSaves.length === 0) {
    recentList.innerHTML = '<div class="empty">저장 기록이 없습니다.</div>';
  } else {
    recentList.innerHTML = recentSaves.slice(0, 5)
      .map(s => `<a href="${s.url}" target="_blank" class="recent-item">${s.name}</a>`)
      .join("");
  }

  // Open synco
  document.getElementById("openSynco").addEventListener("click", async () => {
    const { serverUrl } = await chrome.storage.sync.get("serverUrl");
    chrome.tabs.create({ url: serverUrl || "https://synco.example.com" });
  });

  // Search
  let searchTimeout;
  document.getElementById("searchInput").addEventListener("input", (e) => {
    clearTimeout(searchTimeout);
    const query = e.target.value.trim();
    if (query.length < 2) {
      document.getElementById("searchResults").innerHTML = "";
      return;
    }
    searchTimeout = setTimeout(async () => {
      const result = await chrome.runtime.sendMessage({ type: "SEARCH", query });
      const container = document.getElementById("searchResults");
      if (result.status === "success" && result.data.results.length > 0) {
        container.innerHTML = result.data.results
          .map(c => `
            <a href="${c.synco_url}" target="_blank" class="search-item">
              <strong>${c.name}</strong>
              <span>${c.company || ""} ${c.position || ""}</span>
            </a>
          `).join("");
      } else {
        container.innerHTML = '<div class="empty">검색 결과가 없습니다.</div>';
      }
    }, 300);
  });
});
