(function () {
  "use strict";

  var _tabChangedHandler = null;
  var _afterSettleHandler = null;

  function initTabBadges() {
    var projectPk = document.querySelector("[data-project-pk]");
    if (!projectPk) return;
    projectPk = projectPk.getAttribute("data-project-pk");

    document.querySelectorAll("[data-tab-bar] [data-tab]").forEach(function (btn) {
      var tab = btn.getAttribute("data-tab");
      var badge = btn.querySelector("[data-badge-count]");
      if (!badge) return;

      var latestStr = badge.getAttribute("data-latest");
      if (!latestStr) return;

      var latest = new Date(latestStr).getTime();
      var lastViewed = parseInt(
        sessionStorage.getItem("lastViewed_" + projectPk + "_" + tab) || "0",
        10
      );

      if (latest > lastViewed) {
        badge.setAttribute("data-badge-new", "true");
        badge.classList.add("ring-2", "ring-blue-400");
      }
    });
  }

  function handleTabChanged(e) {
    var activeTab = e.detail.activeTab;
    if (!activeTab) return;

    var tabBar = document.querySelector("[data-tab-bar]");
    if (!tabBar) return;

    // 모든 탭 버튼에서 active 클래스 제거, 해당 탭에 추가
    tabBar.querySelectorAll("[data-tab]").forEach(function (btn) {
      var tab = btn.getAttribute("data-tab");
      if (tab === activeTab) {
        btn.classList.remove(
          "border-transparent",
          "text-gray-500",
          "hover:text-gray-700",
          "hover:border-gray-300"
        );
        btn.classList.add("border-primary", "text-primary");
      } else {
        btn.classList.remove("border-primary", "text-primary");
        btn.classList.add(
          "border-transparent",
          "text-gray-500",
          "hover:text-gray-700",
          "hover:border-gray-300"
        );
      }
    });

    // 뱃지 신규 표시 갱신: 현재 탭의 lastViewed 타임스탬프 업데이트
    var projectEl = document.querySelector("[data-project-pk]");
    var projectPk = projectEl ? projectEl.getAttribute("data-project-pk") : null;
    if (projectPk) {
      sessionStorage.setItem(
        "lastViewed_" + projectPk + "_" + activeTab,
        Date.now().toString()
      );
      // 현재 탭의 신규 표시 제거
      var badge = tabBar.querySelector(
        '[data-tab="' + activeTab + '"] [data-badge-new]'
      );
      if (badge) {
        badge.removeAttribute("data-badge-new");
        badge.classList.remove("ring-2", "ring-blue-400");
      }
    }
  }

  function cleanup() {
    if (_tabChangedHandler) {
      document.body.removeEventListener("tabChanged", _tabChangedHandler);
      _tabChangedHandler = null;
    }
  }

  function init() {
    cleanup();
    _tabChangedHandler = handleTabChanged;
    document.body.addEventListener("tabChanged", _tabChangedHandler);
    initTabBadges();
  }

  // Re-initialize after HTMX swaps
  _afterSettleHandler = function () {
    // Only re-init if project detail page is present
    if (document.querySelector("[data-tab-bar]")) {
      init();
    }
  };
  document.addEventListener("htmx:afterSettle", _afterSettleHandler);

  // Initial setup
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
