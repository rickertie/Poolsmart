/* PoolSmart docs — tiny enhancements, no framework */
(function () {
  // Add accessible labels to external links
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll('a[href^="http"]').forEach(function (a) {
      if (a.hostname !== location.hostname && !a.getAttribute("aria-label")) {
        var label = (a.textContent || a.getAttribute("aria-label") || "External link").trim();
        a.setAttribute("aria-label", label + " (opens in new tab)");
        if (!a.hasAttribute("target")) return; // let MkDocs handle target
      }
    });
    // Ensure tables have captions for screen readers if missing header scope already handled by Material
    document.querySelectorAll(".md-typeset table:not([class]) th").forEach(function (th) {
      th.setAttribute("scope", "col");
    });
  });
})();
