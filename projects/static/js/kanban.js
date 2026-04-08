/**
 * Kanban board drag-and-drop via Sortable.js.
 * Each .kanban-cards container becomes a connected sortable group.
 * On drop, sends PATCH to /projects/<id>/status/ with new status.
 */
(function () {
  function getCsrfToken() {
    var el = document.querySelector("[hx-headers]");
    if (el) {
      try {
        var headers = JSON.parse(el.getAttribute("hx-headers"));
        return headers["X-CSRFToken"] || "";
      } catch (e) {
        return "";
      }
    }
    return "";
  }

  document.querySelectorAll(".kanban-cards").forEach(function (el) {
    new Sortable(el, {
      group: "kanban",
      animation: 150,
      ghostClass: "opacity-30",
      dragClass: "shadow-lg",
      onEnd: function (evt) {
        var projectId = evt.item.dataset.projectId;
        var newStatus = evt.to.dataset.status;

        if (!projectId || !newStatus) return;

        fetch("/projects/" + projectId + "/status/", {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCsrfToken(),
          },
          body: JSON.stringify({ status: newStatus }),
        });
      },
    });
  });
})();
