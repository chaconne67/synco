(async function () {
  const { parserJobkorea } = await chrome.storage.sync.get({ parserJobkorea: true });
  if (!parserJobkorea) return;

  const JobkoreaParser = {
    parse() {
      const getText = (sel) => document.querySelector(sel)?.textContent?.trim() || "";

      const name = getText(".resume-name") || getText(".name");
      const position = getText(".resume-title") || getText(".position");
      const company = getText(".company-name") || getText(".current-company");

      const careers = [];
      document.querySelectorAll(".career-item, .experience-item").forEach((item) => {
        careers.push({
          company: item.querySelector(".company")?.textContent?.trim() || "",
          position: item.querySelector(".position, .title")?.textContent?.trim() || "",
          department: item.querySelector(".department")?.textContent?.trim() || "",
          start_date: item.querySelector(".period .start, .date-start")?.textContent?.trim() || "",
          end_date: item.querySelector(".period .end, .date-end")?.textContent?.trim() || "",
          is_current: "false",
          duties: item.querySelector(".duties, .description")?.textContent?.trim() || "",
        });
      });

      const educations = [];
      document.querySelectorAll(".education-item, .edu-item").forEach((item) => {
        const years = (item.querySelector(".period, .date")?.textContent || "").match(/\d{4}/g) || [];
        educations.push({
          institution: item.querySelector(".school, .institution")?.textContent?.trim() || "",
          degree: item.querySelector(".degree")?.textContent?.trim() || "",
          major: item.querySelector(".major")?.textContent?.trim() || "",
          start_year: years[0] || "",
          end_year: years[1] || "",
        });
      });

      let quality = "complete";
      if (!name) quality = "failed";
      else if (!company && careers.length === 0) quality = "partial";

      return {
        name, current_company: company, current_position: position,
        address: "", email: "", phone: "",
        external_profile_url: location.href.split("?")[0],
        careers, educations, skills: [],
        source_site: "jobkorea", source_url: location.href,
        parse_quality: quality,
      };
    },
  };

  async function init() {
    const shadow = SyncoOverlay.create();
    if (!shadow) return;

    const authResult = await chrome.runtime.sendMessage({ type: "CHECK_AUTH" });
    if (authResult.status !== "success") {
      SyncoOverlay.setStatus("synco에 로그인이 필요합니다.", "error");
      return;
    }

    SyncoOverlay.setStatus("프로필 파싱 중...");
    const profile = JobkoreaParser.parse();

    if (profile.parse_quality === "failed") {
      SyncoOverlay.setStatus("프로필을 파싱할 수 없습니다.", "error");
      return;
    }

    SyncoOverlay.setStatus("중복 확인 중...");
    const dupResult = await chrome.runtime.sendMessage({ type: "CHECK_DUPLICATE", data: profile });

    if (dupResult.status === "duplicate_found") {
      const d = dupResult.data;
      SyncoOverlay.setStatus("DB에 이미 등록된 후보자입니다.", "info");
      SyncoOverlay.showResult(`
        <div class="synco-existing">
          <strong>${d.name}</strong> (${d.company || ""})
          <br><a href="${d.synco_url}" target="_blank" class="synco-link">synco에서 보기</a>
        </div>
      `);
      return;
    }

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
      const result = await chrome.runtime.sendMessage({ type: "SAVE_PROFILE", data: profile });
      if (result.status === "success") {
        SyncoOverlay.setStatus("저장 완료!", "success");
        SyncoOverlay.showResult(`<a href="${result.data.synco_url}" target="_blank" class="synco-link">synco에서 보기</a>`);
      } else {
        SyncoOverlay.setStatus(`저장 실패: ${(result.errors || []).join(", ")}`, "error");
        saving = false;
      }
    });
  }

  setTimeout(() => init(), 1000);
})();
