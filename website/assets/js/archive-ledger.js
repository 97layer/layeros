(function () {
  var ledger = document.getElementById("ledger-list");
  if (!ledger) return;

  var filterButtons = Array.prototype.slice.call(document.querySelectorAll("[data-filter-type]"));
  var searchInput = document.getElementById("archive-search");
  var totalEl = document.getElementById("archive-total");
  var visibleEl = document.getElementById("archive-visible");
  var spotlightTitle = document.getElementById("spotlight-title");
  var spotlightSummary = document.getElementById("spotlight-summary");
  var spotlightType = document.getElementById("spotlight-type");
  var spotlightDate = document.getElementById("spotlight-date");
  var spotlightIssue = document.getElementById("spotlight-issue");
  var spotlightLink = document.getElementById("spotlight-link");

  var TYPE_META = {
    essay: { label: "Essay", caption: "문장과 사유" },
    journal: { label: "Journal", caption: "과정의 단면" },
    lookbook: { label: "Lookbook", caption: "질감과 실루엣" },
    playlist: { label: "Playlist", caption: "시간의 리듬" }
  };

  var allPosts = [];
  var currentFilter = "all";
  var currentQuery = "";
  var selectedPostId = null;

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function dateValue(value) {
    var text = String(value || "").trim();
    if (!text) return 0;
    var normalized = text.replace(/\./g, "-").replace(/\//g, "-");
    var parsed = Date.parse(normalized);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function normalizeType(value) {
    var type = String(value || "").trim().toLowerCase();
    if (type === "journal" || type === "lookbook" || type === "playlist") return type;
    return "essay";
  }

  function resolveUrl(url, slug) {
    var explicit = String(url || "").trim();
    if (explicit && explicit !== "#" && explicit !== "/#") return explicit;
    var cleanSlug = String(slug || "").replace(/^\//, "").replace(/\/$/, "");
    return cleanSlug ? cleanSlug + "/" : "#";
  }

  function normalize(post, index) {
    var slug = String(post.slug || "").replace(/^\//, "").replace(/\/$/, "");
    var summary = String(post.preview || post.summary || "").trim();
    return {
      id: index,
      slug: slug,
      url: resolveUrl(post.url, slug),
      title: post.title || "Untitled",
      summary: summary || "요약 준비 중입니다.",
      date: post.date || "",
      dateValue: dateValue(post.date),
      type: normalizeType(post.type),
      issue: post.issue || ("Issue " + String(index + 1).padStart(3, "0")),
      readMin: typeof post.readMin === "number" ? post.readMin : null
    };
  }

  function sortPosts(posts) {
    return posts.slice().sort(function (a, b) {
      if (b.dateValue !== a.dateValue) return b.dateValue - a.dateValue;
      return a.id - b.id;
    });
  }

  function actionLabel(post) {
    if (post.type === "playlist") return "Play";
    if (typeof post.readMin === "number" && post.readMin > 0) return String(post.readMin) + " MIN";
    if (post.type === "lookbook") return "View";
    return "Read";
  }

  function toneClass(index) {
    return "tone-" + String((index % 4) + 1);
  }

  function updateCount(total, visible) {
    if (totalEl) totalEl.textContent = String(total);
    if (visibleEl) visibleEl.textContent = String(visible);
  }

  function updateSpotlight(post) {
    if (!post) return;

    selectedPostId = post.id;
    var meta = TYPE_META[post.type] || TYPE_META.essay;

    if (spotlightTitle) spotlightTitle.textContent = post.title;
    if (spotlightSummary) spotlightSummary.textContent = post.summary;
    if (spotlightType) spotlightType.textContent = meta.label;
    if (spotlightDate) spotlightDate.textContent = post.date || "-";
    if (spotlightIssue) spotlightIssue.textContent = post.issue || "-";

    if (spotlightLink) {
      spotlightLink.href = post.url;
      spotlightLink.setAttribute("aria-label", post.title + " 열기");
    }

    var items = ledger.querySelectorAll(".ledger__item--cinema");
    items.forEach(function (item) {
      var itemPostId = Number(item.getAttribute("data-post-id"));
      item.classList.toggle("is-spotlight", itemPostId === selectedPostId);
    });
  }

  function renderLedger(posts) {
    updateCount(allPosts.length, posts.length);

    if (!posts.length) {
      ledger.innerHTML = '<li class="ledger__placeholder">표시할 기록이 없습니다.</li>';
      if (spotlightTitle) spotlightTitle.textContent = "No entries";
      if (spotlightSummary) spotlightSummary.textContent = "필터 또는 검색 조건을 조정해 주세요.";
      if (spotlightType) spotlightType.textContent = "-";
      if (spotlightDate) spotlightDate.textContent = "-";
      if (spotlightIssue) spotlightIssue.textContent = "-";
      if (spotlightLink) spotlightLink.setAttribute("href", "#");
      return;
    }

    var items = posts.map(function (post, index) {
      var serial = String(index + 1).padStart(3, "0");
      var meta = TYPE_META[post.type] || TYPE_META.essay;
      var isSpotlight = selectedPostId === post.id ? " is-spotlight" : "";

      return [
        '<li class="ledger__item ledger__item--cinema ',
        toneClass(index),
        isSpotlight,
        '" data-type="',
        escapeHtml(post.type),
        '" data-post-id="',
        String(post.id),
        '">',
        '<a class="ledger__hit" href="',
        escapeHtml(post.url),
        '" data-post-id="',
        String(post.id),
        '">',
        '<div class="ledger__body">',
        '<div class="ledger__meta">',
        '<span class="ledger__serial">',
        serial,
        "</span>",
        '<span class="ledger__type">',
        escapeHtml(meta.label),
        "</span>",
        "<span>",
        escapeHtml(post.issue),
        "</span>",
        "<span>",
        escapeHtml(post.date),
        "</span>",
        "</div>",
        '<h2 class="ledger__title">',
        escapeHtml(post.title),
        "</h2>",
        '<p class="ledger__summary">',
        escapeHtml(post.summary),
        "</p>",
        '<div class="ledger__foot">',
        '<span class="ledger__caption">',
        escapeHtml(meta.caption),
        "</span>",
        '<span class="ledger__action">',
        escapeHtml(actionLabel(post)),
        "</span>",
        "</div>",
        "</div>",
        '<figure class="ledger__film ledger__film--',
        escapeHtml(post.type),
        '" aria-hidden="true">',
        '<span class="ledger__film-code">',
        escapeHtml(meta.label.toUpperCase()),
        " ",
        serial,
        "</span>",
        '<span class="ledger__film-issue">',
        escapeHtml(post.issue),
        "</span>",
        "</figure>",
        "</a>",
        "</li>"
      ].join("");
    });

    ledger.innerHTML = items.join("");

    var links = Array.prototype.slice.call(ledger.querySelectorAll(".ledger__hit"));
    links.forEach(function (link) {
      var postId = Number(link.getAttribute("data-post-id"));
      var post = allPosts.find(function (candidate) { return candidate.id === postId; });
      if (!post) return;
      link.addEventListener("mouseenter", function () {
        updateSpotlight(post);
      });
      link.addEventListener("focus", function () {
        updateSpotlight(post);
      });
    });
  }

  function getVisiblePosts() {
    return allPosts.filter(function (post) {
      var typeMatch = currentFilter === "all" || post.type === currentFilter;
      if (!typeMatch) return false;
      if (!currentQuery) return true;
      var haystack = (post.title + " " + post.summary + " " + post.issue).toLowerCase();
      return haystack.indexOf(currentQuery) !== -1;
    });
  }

  function applyState() {
    filterButtons.forEach(function (btn) {
      btn.classList.toggle("is-active", btn.dataset.filterType === currentFilter);
    });

    var visible = getVisiblePosts();
    renderLedger(visible);
    if (visible.length) {
      var selected = visible.find(function (post) { return post.id === selectedPostId; });
      updateSpotlight(selected || visible[0]);
    }
  }

  fetch("index.json")
    .then(function (response) {
      if (!response.ok) throw new Error("index.json load failed");
      return response.json();
    })
    .then(function (raw) {
      if (!Array.isArray(raw)) raw = [];
      allPosts = sortPosts(raw.map(normalize));
      applyState();
      document.body.classList.add("archive-cinema-ready");
    })
    .catch(function () {
      allPosts = [];
      applyState();
    });

  filterButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      currentFilter = btn.dataset.filterType || "all";
      applyState();
    });
  });

  if (searchInput) {
    searchInput.addEventListener("input", function () {
      currentQuery = String(searchInput.value || "").trim().toLowerCase();
      applyState();
    });
  }
})();
