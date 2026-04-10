(async function () {
  // Check if parser is enabled
  const { parserLinkedin } = await chrome.storage.sync.get({ parserLinkedin: true });
  if (!parserLinkedin) return;

  // Only activate on /in/ profile pages
  if (!location.pathname.match(/^\/in\/[^/]+\/?$/)) return;

  const LinkedInParser = {
    parse() {
      const getText = (sel) => document.querySelector(sel)?.textContent?.trim() || "";
      const getAll = (sel) => [...document.querySelectorAll(sel)];

      const name = getText(".text-heading-xlarge") || getText("h1");
      const position = getText(".text-body-medium.break-words");
      const company = getText(".inline-show-more-text--is-collapsed") ||
        getText(".pv-text-details__right-panel-item-text");
      const address = getText(".text-body-small.inline.t-black--light.break-words");

      // Experience section
      const careers = [];
      const expItems = getAll("#experience ~ .pvs-list__outer-container .pvs-entity--padded");
      for (const item of expItems) {
        const title = item.querySelector(".mr1.hoverable-link-text.t-bold span")?.textContent?.trim() || "";
        const comp = item.querySelector(".t-14.t-normal span")?.textContent?.trim() || "";
        const dates = item.querySelector(".t-14.t-normal.t-black--light span")?.textContent?.trim() || "";
        const [startDate, endDate] = (dates.split(" - ").map(d => d.trim()));
        const isCurrent = (endDate || "").toLowerCase().includes("present") ||
          (endDate || "").includes("현재");
        careers.push({
          company: comp.split(" · ")[0] || "",
          position: title,
          department: "",
          start_date: startDate || "",
          end_date: isCurrent ? "" : (endDate || ""),
          is_current: isCurrent ? "true" : "false",
          duties: "",
        });
      }

      // Education section
      const educations = [];
      const eduItems = getAll("#education ~ .pvs-list__outer-container .pvs-entity--padded");
      for (const item of eduItems) {
        const institution = item.querySelector(".mr1.hoverable-link-text.t-bold span")?.textContent?.trim() || "";
        const degreeInfo = item.querySelector(".t-14.t-normal span")?.textContent?.trim() || "";
        const [degree, major] = degreeInfo.split(",").map(s => s.trim());
        const dateSpan = item.querySelector(".t-14.t-normal.t-black--light span")?.textContent?.trim() || "";
        const years = dateSpan.match(/\d{4}/g) || [];
        educations.push({
          institution,
          degree: degree || "",
          major: major || "",
          start_year: years[0] || "",
          end_year: years[1] || "",
        });
      }

      // Skills
      const skills = getAll("#skills ~ .pvs-list__outer-container .pvs-entity--padded")
        .map(el => el.querySelector(".mr1.hoverable-link-text.t-bold span")?.textContent?.trim())
        .filter(Boolean)
        .slice(0, 20);

      // Parse quality assessment
      let quality = "complete";
      if (!name) quality = "failed";
      else if (!company && careers.length === 0) quality = "partial";

      return {
        name,
        current_company: company,
        current_position: position,
        address,
        email: "",
        phone: "",
        external_profile_url: location.href.split("?")[0],
        careers,
        educations,
        skills,
        source_site: "linkedin",
        source_url: location.href,
        parse_quality: quality,
      };
    },
  };

  async function init() {
    const shadow = SyncoOverlay.create();
    if (!shadow) return;

    // 1. Check auth
    const authResult = await chrome.runtime.sendMessage({ type: "CHECK_AUTH" });
    if (authResult.status !== "success") {
      SyncoOverlay.setStatus("synco에 로그인이 필요합니다.", "error");
      return;
    }

    // 2. Parse profile
    SyncoOverlay.setStatus("프로필 파싱 중...");
    const profile = LinkedInParser.parse();

    if (profile.parse_quality === "failed") {
      SyncoOverlay.setStatus("프로필을 파싱할 수 없습니다.", "error");
      return;
    }

    // 3. Check duplicate
    SyncoOverlay.setStatus("중복 확인 중...");
    const dupResult = await chrome.runtime.sendMessage({
      type: "CHECK_DUPLICATE",
      data: profile,
    });

    if (dupResult.status === "duplicate_found") {
      const d = dupResult.data;
      SyncoOverlay.setStatus("DB에 이미 등록된 후보자입니다.", "info");
      SyncoOverlay.showResult(`
        <div class="synco-existing">
          <strong>${d.name}</strong> (${d.company || ""})
          <br><small>${d.match_reason}로 매칭</small>
          <br><a href="${d.synco_url}" target="_blank" class="synco-link">synco에서 보기</a>
        </div>
      `);
      return;
    }

    if (dupResult.status === "possible_match") {
      SyncoOverlay.setStatus("유사한 후보자가 있습니다.", "warning");
      const matches = dupResult.data.possible_matches
        .map(m => `<div class="synco-match-item">${m.name} (${m.company}) <a href="${m.synco_url}" target="_blank">보기</a></div>`)
        .join("");
      SyncoOverlay.showResult(matches);
    }

    // 4. Show save button
    SyncoOverlay.setStatus(
      profile.parse_quality === "partial" ? "부분 파싱 완료" : "파싱 완료",
      profile.parse_quality === "partial" ? "warning" : "success"
    );

    let saving = false;
    SyncoOverlay.showActions(`
      <button class="synco-btn synco-btn-save">저장</button>
      <span class="synco-parsed-info">${profile.name} | ${profile.current_company || "회사 미확인"}</span>
    `);

    SyncoOverlay.addActionListener(".synco-btn-save", async () => {
      if (saving) return;
      saving = true;

      SyncoOverlay.setStatus("저장 중...");
      const result = await chrome.runtime.sendMessage({
        type: "SAVE_PROFILE",
        data: profile,
      });

      if (result.status === "success") {
        SyncoOverlay.setStatus("저장 완료!", "success");
        SyncoOverlay.showResult(`
          <a href="${result.data.synco_url}" target="_blank" class="synco-link">synco에서 보기</a>
        `);
        // Save to recent list
        const { recentSaves = [] } = await chrome.storage.local.get("recentSaves");
        recentSaves.unshift({
          name: result.data.name,
          url: result.data.synco_url,
          savedAt: new Date().toISOString(),
        });
        await chrome.storage.local.set({ recentSaves: recentSaves.slice(0, 20) });

        // Increment today's count
        const todayKey = `saves_${new Date().toISOString().slice(0, 10)}`;
        const counts = await chrome.storage.local.get(todayKey);
        await chrome.storage.local.set({ [todayKey]: (counts[todayKey] || 0) + 1 });
      } else if (result.status === "duplicate_found") {
        SyncoOverlay.setStatus("이미 등록된 후보자입니다.", "info");
        // Show diff and update option
        const d = result.data;
        if (d.diff && Object.keys(d.diff).length > 0) {
          const diffHtml = Object.entries(d.diff)
            .filter(([k]) => !k.startsWith("new_"))
            .map(([k, v]) => `<div class="synco-diff-item">${k}: ${v.old} → ${v.new}</div>`)
            .join("");
          SyncoOverlay.showResult(`
            <div class="synco-existing">
              <strong>변경 사항이 있습니다:</strong>
              ${diffHtml}
              <button class="synco-btn synco-btn-update">업데이트</button>
            </div>
          `);
          SyncoOverlay.addActionListener(".synco-btn-update", async () => {
            const updateData = {
              ...profile,
              update_mode: true,
              candidate_id: d.candidate_id,
              fields: Object.keys(d.diff).filter(k => !k.startsWith("new_")),
              new_careers_confirmed: d.diff.new_careers || [],
              new_educations_confirmed: d.diff.new_educations || [],
            };
            const updateResult = await chrome.runtime.sendMessage({
              type: "SAVE_PROFILE",
              data: updateData,
            });
            if (updateResult.status === "success") {
              SyncoOverlay.setStatus("업데이트 완료!", "success");
            } else {
              SyncoOverlay.setStatus("업데이트 실패", "error");
            }
          });
        }
      } else {
        SyncoOverlay.setStatus(`저장 실패: ${(result.errors || []).join(", ")}`, "error");
        saving = false;
      }
    });
  }

  // LinkedIn SPA navigation handling
  let lastUrl = location.href;
  const urlObserver = new MutationObserver(() => {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      SyncoOverlay.remove();
      if (location.pathname.match(/^\/in\/[^/]+\/?$/)) {
        setTimeout(() => init(), 1500);
      }
    }
  });
  urlObserver.observe(document.body, { childList: true, subtree: true });

  // Initial run (wait for DOM to settle)
  setTimeout(() => init(), 1000);
})();
