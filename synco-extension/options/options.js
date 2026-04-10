document.addEventListener("DOMContentLoaded", async () => {
  const settings = await chrome.storage.sync.get({
    serverUrl: "",
    parserLinkedin: true,
    parserJobkorea: true,
    parserSaramin: true,
  });

  document.getElementById("serverUrl").value = settings.serverUrl;
  document.getElementById("linkedin").checked = settings.parserLinkedin;
  document.getElementById("jobkorea").checked = settings.parserJobkorea;
  document.getElementById("saramin").checked = settings.parserSaramin;

  document.getElementById("testBtn").addEventListener("click", async () => {
    const statusEl = document.getElementById("testStatus");
    const url = document.getElementById("serverUrl").value.trim();
    if (!url) {
      statusEl.textContent = "서버 URL을 입력하세요.";
      statusEl.className = "status error";
      return;
    }

    statusEl.textContent = "연결 중...";
    statusEl.className = "status";

    try {
      const response = await fetch(`${url}/candidates/extension/auth-status/`, {
        credentials: "include",
      });
      const data = await response.json();
      if (data.status === "success") {
        statusEl.textContent = `연결 성공! 사용자: ${data.data.user}, 조직: ${data.data.organization || "없음"}`;
        statusEl.className = "status success";
      } else {
        statusEl.textContent = "인증 필요: synco에 먼저 로그인하세요.";
        statusEl.className = "status error";
      }
    } catch (e) {
      statusEl.textContent = `연결 실패: ${e.message}`;
      statusEl.className = "status error";
    }
  });

  document.getElementById("saveBtn").addEventListener("click", async () => {
    await chrome.storage.sync.set({
      serverUrl: document.getElementById("serverUrl").value.trim(),
      parserLinkedin: document.getElementById("linkedin").checked,
      parserJobkorea: document.getElementById("jobkorea").checked,
      parserSaramin: document.getElementById("saramin").checked,
    });
    const statusEl = document.getElementById("saveStatus");
    statusEl.textContent = "저장되었습니다.";
    statusEl.className = "status success";
    setTimeout(() => { statusEl.textContent = ""; }, 2000);
  });
});
