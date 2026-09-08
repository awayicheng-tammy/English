(function () {
  "use strict";

  var mainEl = document.getElementById("app-main");
  var crumbsEl = document.getElementById("crumbs");

  function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function getIssues() {
    return window.ISSUE_MANIFEST || [];
  }

  function getIssueData(slug) {
    return (window.ISSUES || {})[slug];
  }

  function setCrumbs(parts) {
    crumbsEl.innerHTML = parts
      .map(function (p, i) {
        if (i === parts.length - 1) return escapeHtml(p.label);
        return '<a href="' + p.href + '">' + escapeHtml(p.label) + "</a>";
      })
      .join(" &rsaquo; ");
  }

  function renderHome() {
    setCrumbs([{ label: "目录" }]);
    var issues = getIssues();
    if (issues.length === 0) {
      mainEl.innerHTML =
        '<p class="empty-state">还没有生成任何一期。运行 ' +
        "<code>python3 scripts/extract_articles.py &lt;PDF文件&gt;</code> " +
        "来处理一本 PDF，然后刷新这个页面。</p>";
      return;
    }
    var html = issues
      .map(function (issue) {
        var data = getIssueData(issue.slug);
        var count = data ? data.articles.length : 0;
        return (
          '<a class="issue-card" href="#/issue/' +
          encodeURIComponent(issue.slug) +
          '"><h2>' +
          escapeHtml(issue.title) +
          "</h2><p>" +
          count +
          " 篇文章</p></a>"
        );
      })
      .join("");
    mainEl.innerHTML = html;
  }

  function renderIssue(slug) {
    var data = getIssueData(slug);
    if (!data) {
      mainEl.innerHTML = '<p class="empty-state">找不到这一期。</p>';
      setCrumbs([{ label: "目录", href: "#/" }, { label: slug }]);
      return;
    }
    setCrumbs([{ label: "目录", href: "#/" }, { label: data.title }]);

    var bySection = {};
    var order = [];
    data.articles.forEach(function (a) {
      var sec = a.section || "其他";
      if (!bySection[sec]) {
        bySection[sec] = [];
        order.push(sec);
      }
      bySection[sec].push(a);
    });

    var html = order
      .map(function (sec) {
        var rows = bySection[sec]
          .map(function (a) {
            return (
              '<a class="article-row" href="#/issue/' +
              encodeURIComponent(slug) +
              "/article/" +
              encodeURIComponent(a.id) +
              '"><div class="title">' +
              escapeHtml(a.title) +
              "</div>" +
              (a.dek ? '<div class="dek">' + escapeHtml(a.dek) + "</div>" : "") +
              "</a>"
            );
          })
          .join("");
        return (
          '<div class="section-group"><h2>' +
          escapeHtml(sec) +
          "</h2>" +
          rows +
          "</div>"
        );
      })
      .join("");
    mainEl.innerHTML = html;
  }

  function renderArticle(slug, articleId) {
    var data = getIssueData(slug);
    if (!data) {
      mainEl.innerHTML = '<p class="empty-state">找不到这一期。</p>';
      return;
    }
    var idx = data.articles.findIndex(function (a) {
      return a.id === articleId;
    });
    if (idx === -1) {
      mainEl.innerHTML = '<p class="empty-state">找不到这篇文章。</p>';
      setCrumbs([{ label: "目录", href: "#/" }, { label: data.title, href: "#/issue/" + encodeURIComponent(slug) }]);
      return;
    }
    var a = data.articles[idx];
    setCrumbs([
      { label: "目录", href: "#/" },
      { label: data.title, href: "#/issue/" + encodeURIComponent(slug) },
      { label: a.title },
    ]);

    var prev = data.articles[idx - 1];
    var next = data.articles[idx + 1];
    var issueHref = "#/issue/" + encodeURIComponent(slug);

    var paragraphsHtml = a.paragraphs
      .map(function (p) {
        return "<p>" + escapeHtml(p) + "</p>";
      })
      .join("");

    var navHtml =
      '<nav class="article-nav">' +
      (prev
        ? '<a class="prev" href="#/issue/' + encodeURIComponent(slug) + "/article/" + encodeURIComponent(prev.id) + '">← ' + escapeHtml(prev.title) + "</a>"
        : '<span class="placeholder">-</span>') +
      (next
        ? '<a class="next" href="#/issue/' + encodeURIComponent(slug) + "/article/" + encodeURIComponent(next.id) + '">' + escapeHtml(next.title) + " →</a>"
        : '<span class="placeholder">-</span>') +
      "</nav>";

    mainEl.innerHTML =
      '<a class="back-link" href="' + issueHref + '">← 返回目录</a>' +
      '<article class="reader">' +
      '<div class="section-label">' + escapeHtml(a.section || "") + "</div>" +
      "<h1>" + escapeHtml(a.title) + "</h1>" +
      (a.dek ? '<div class="dek">' + escapeHtml(a.dek) + "</div>" : "") +
      paragraphsHtml +
      "</article>" +
      navHtml;
    window.scrollTo(0, 0);
  }

  function route() {
    var hash = window.location.hash.replace(/^#/, "") || "/";
    var parts = hash.split("/").filter(Boolean);
    // parts: [] -> home; ["issue", slug] -> issue toc; ["issue", slug, "article", id] -> article
    if (parts.length === 0) {
      renderHome();
    } else if (parts[0] === "issue" && parts.length === 2) {
      renderIssue(decodeURIComponent(parts[1]));
    } else if (parts[0] === "issue" && parts.length === 4 && parts[2] === "article") {
      renderArticle(decodeURIComponent(parts[1]), decodeURIComponent(parts[3]));
    } else {
      renderHome();
    }
  }

  window.addEventListener("hashchange", route);
  window.addEventListener("DOMContentLoaded", route);
  document.getElementById("brand").addEventListener("click", function () {
    window.location.hash = "#/";
  });
})();
