// webapp/static/app.js

const state = {
  emails: [],          // EmailOverview[]
  filteredEmails: [],
  selectedId: null,    // uid of selected email
  selectedOverview: null,
  filterSenderKey: null,
  searchText: "",
  page: 1,
  pageSize: 20,
  colorMap: {},        // sender/domain -> color
  currentMailbox: "INBOX",
};

const COLOR_PALETTE = [
  "#f97316", // orange
  "#22c55e", // green
  "#0ea5e9", // sky
  "#a855f7", // purple
  "#ec4899", // pink
  "#eab308", // yellow
  "#10b981", // emerald
  "#f97373", // soft red
];

document.addEventListener("DOMContentLoaded", () => {
  const refreshBtn = document.getElementById("refresh-btn");
  const pageSizeSelect = document.getElementById("page-size-select");
  const prevPageBtn = document.getElementById("prev-page-btn");
  const nextPageBtn = document.getElementById("next-page-btn");
  const searchInput = document.getElementById("search-input");
  const clearFiltersBtn = document.getElementById("clear-filters-btn");

  if (refreshBtn) refreshBtn.addEventListener("click", () => fetchOverview());
  if (prevPageBtn) prevPageBtn.addEventListener("click", () => changePage(-1));
  if (nextPageBtn) nextPageBtn.addEventListener("click", () => changePage(1));
  if (pageSizeSelect) {
    pageSizeSelect.addEventListener("change", () => {
      state.pageSize = Number(pageSizeSelect.value || 20);
      state.page = 1;
      applyFiltersAndRender();
    });
  }
  if (searchInput) {
    searchInput.addEventListener("input", () => {
      state.searchText = searchInput.value.trim().toLowerCase();
      state.page = 1;
      applyFiltersAndRender();
    });
  }
  if (clearFiltersBtn) {
    clearFiltersBtn.addEventListener("click", () => {
      state.filterSenderKey = null;
      state.searchText = "";
      state.page = 1;
      const searchInput = document.getElementById("search-input");
      if (searchInput) searchInput.value = "";
      setCurrentFilterLabel();
      applyFiltersAndRender();
      highlightLegendSelection();
    });
  }

  // Initial load
  fetchMailboxes();
  fetchOverview();
});

/* ------------------ API calls ------------------ */

async function fetchMailboxes() {
  try {
    const res = await fetch("/api/emails/mailbox");
    if (!res.ok) throw new Error("Failed to fetch mailboxes");
    const data = await res.json(); // { accountName: [mailbox1, mailbox2], ... }
    renderMailboxList(data);
  } catch (err) {
    console.error("Error fetching mailboxes:", err);
  }
}

async function fetchOverview() {
  try {
    // adjust n if you want more than default 50
    const params = new URLSearchParams({
      mailbox: state.currentMailbox,
      n: "200",
    });
    const res = await fetch(`/api/emails/overview?${params.toString()}`);
    if (!res.ok) throw new Error("Failed to fetch emails overview");
    const data = await res.json();
    state.emails = Array.isArray(data) ? data : [];
    buildColorMap();
    buildLegend();
    state.page = 1;
    applyFiltersAndRender();
  } catch (err) {
    console.error("Error fetching overview:", err);
    renderError("Failed to fetch emails.");
  }
}

async function fetchEmailDetail(overview) {
  if (!overview) {
    renderDetailFromOverviewOnly(overview);
    return;
  }

  const ref = overview.ref || {};

  const account = ref.account || overview.account;
  const mailbox = ref.mailbox || overview.mailbox;
  const uid = ref.uid;

  if (!account || !mailbox || uid == null) {
    // Fallback: cannot route to detail endpoint, show overview only
    renderDetailFromOverviewOnly(overview);
    return;
  }

  const accountEnc = encodeURIComponent(account);
  const mailboxEnc = encodeURIComponent(mailbox);
  const uidEnc = encodeURIComponent(uid);

  try {
    const res = await fetch(
      `/api/accounts/${accountEnc}/mailboxes/${mailboxEnc}/emails/${uidEnc}`
    );
    if (!res.ok) throw new Error("Failed to fetch email detail");
    const msg = await res.json();
    renderDetailFromMessage(overview, msg);
  } catch (err) {
    console.error("Error fetching email detail:", err);
    renderDetailFromOverviewOnly(overview);
  }
}

/* ------------------ State utilities ------------------ */

function buildColorMap() {
  const map = {};
  let colorIndex = 0;

  for (const email of state.emails) {
    const key = getSenderKey(email);
    if (!map[key]) {
      map[key] = COLOR_PALETTE[colorIndex % COLOR_PALETTE.length];
      colorIndex++;
    }
  }
  state.colorMap = map;
}

function getSenderKey(email) {
  if (!email) return "unknown";

  const fromObj = email.from_email || {};
  const addr = fromObj.email || fromObj.name || "";

  if (!addr) return "unknown";

  const parts = String(addr).split("@");
  if (parts.length === 2) return parts[1].toLowerCase();
  return addr.toLowerCase();
}

function getColorForEmail(email) {
  const key = getSenderKey(email);
  return state.colorMap[key] || "#9ca3af";
}

function formatAddress(addr) {
  if (!addr) return "";
  if (addr.name) return `${addr.name} <${addr.email || ""}>`.trim();
  return addr.email || "";
}

function formatAddressList(list) {
  if (!Array.isArray(list)) return "";
  return list.map(formatAddress).filter(Boolean).join(", ");
}

/* ------------------ Filtering & rendering ------------------ */

function applyFiltersAndRender() {
  let filtered = [...state.emails];

  if (state.filterSenderKey) {
    filtered = filtered.filter((e) => getSenderKey(e) === state.filterSenderKey);
  }

  if (state.searchText) {
    filtered = filtered.filter((e) => {
      const subject = (e.subject || "").toLowerCase();
      const snippet = (e.snippet || "").toLowerCase();
      const bodyPreview = (e.preview || "").toLowerCase();
      return (
        subject.includes(state.searchText) ||
        snippet.includes(state.searchText) ||
        bodyPreview.includes(state.searchText)
      );
    });
  }

  state.filteredEmails = filtered;
  setTotalCountLabel();
  setCurrentFilterLabel();
  renderListAndPagination();
  renderDetail();
}

function renderListAndPagination() {
  const listEl = document.getElementById("email-list");
  const emptyEl = document.getElementById("list-empty");
  const pageInfoEl = document.getElementById("page-info");
  const prevBtn = document.getElementById("prev-page-btn");
  const nextBtn = document.getElementById("next-page-btn");

  if (!listEl || !emptyEl || !pageInfoEl) return;

  const total = state.filteredEmails.length;
  const pageSize = state.pageSize || 20;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  if (state.page > totalPages) state.page = totalPages;

  const startIndex = (state.page - 1) * pageSize;
  const endIndex = startIndex + pageSize;
  const slice = state.filteredEmails.slice(startIndex, endIndex);

  listEl.innerHTML = "";

  if (!slice.length) {
    emptyEl.classList.remove("hidden");
  } else {
    emptyEl.classList.add("hidden");
  }

  for (const email of slice) {
    const card = document.createElement("div");
    card.className = "email-card";
    const ref = email.ref || {};
    card.dataset.uid = ref.uid != null ? ref.uid : "";
    card.dataset.account = ref.account || email.account || "";
    card.dataset.mailbox = ref.mailbox || email.mailbox || "";

    if (email.uid === state.selectedId) {
      card.classList.add("selected");
    }

    const color = getColorForEmail(email);
    const fromObj = email.from_email || {};
    const fromAddr =
      fromObj.name ||
      fromObj.email ||
      "(unknown sender)";
    const toAddr = formatAddressList(email.to);
    const dateStr = formatDate(email.date);
    const subj = email.subject || "(no subject)";
    const snippet = email.preview || "";

    card.innerHTML = `
      <div class="email-color-strip" style="background: ${color};"></div>
      <div class="email-main">
        <div class="email-row-top">
          <div class="email-from">${escapeHtml(fromAddr)}</div>
          <div class="email-date">${escapeHtml(dateStr)}</div>
        </div>
        <div class="email-subject">${escapeHtml(subj)}</div>
        <div class="email-snippet">${escapeHtml(snippet)}</div>
      </div>
    `;

    card.addEventListener("click", () => {
      state.selectedId = email.uid;
      state.selectedOverview = email;
      renderListAndPagination(); // update selection
      // fetch detail from backend
      fetchEmailDetail(email);
    });

    listEl.appendChild(card);
  }

  pageInfoEl.textContent = `Page ${state.page} / ${totalPages}`;

  if (prevBtn) prevBtn.disabled = state.page <= 1;
  if (nextBtn) nextBtn.disabled = state.page >= totalPages;
}

function changePage(delta) {
  const total = state.filteredEmails.length;
  const pageSize = state.pageSize || 20;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const newPage = state.page + delta;
  if (newPage < 1 || newPage > totalPages) return;
  state.page = newPage;
  renderListAndPagination();
}

/* ------------------ Detail rendering ------------------ */

function renderDetail() {
  const placeholder = document.getElementById("detail-placeholder");
  const detail = document.getElementById("email-detail");
  if (!placeholder || !detail) return;

  if (!state.selectedOverview) {
    placeholder.classList.remove("hidden");
    detail.classList.add("hidden");
    return;
  }

  // Detail is rendered after we fetch from API (or from overview fallback)
}

function renderDetailFromOverviewOnly(overview) {
  const placeholder = document.getElementById("detail-placeholder");
  const detail = document.getElementById("email-detail");
  if (!placeholder || !detail || !overview) return;

  placeholder.classList.add("hidden");
  detail.classList.remove("hidden");

  const subjectEl = document.getElementById("detail-subject");
  const fromEl = document.getElementById("detail-from");
  const toEl = document.getElementById("detail-to");
  const dtEl = document.getElementById("detail-datetime");
  const accountEl = document.getElementById("detail-account");
  const bodyEl = document.getElementById("detail-body");
  const badgeEl = document.getElementById("detail-color-badge");

  const fromObj = overview.from_email || {};
  const fromAddr =
    fromObj.name ||
    fromObj.email ||
    "(unknown sender)";
  const toAddr = formatAddressList(overview.to);
  const dateVerbose = formatDate(overview.date, true);
  const color = getColorForEmail(overview);

  if (subjectEl) subjectEl.textContent = overview.subject || "(no subject)";
  if (fromEl) fromEl.textContent = `From: ${fromAddr}`;
  if (toEl) toEl.textContent = toAddr ? `To: ${toAddr}` : "";
  if (dtEl) dtEl.textContent = `Date: ${dateVerbose}`;

  const ref = overview.ref || {};
  if (accountEl) {
    const account = ref.account || overview.account || "all";
    const mailbox = ref.mailbox || overview.mailbox || state.currentMailbox;
    accountEl.textContent = `Account: ${account} • Mailbox: ${mailbox}`;
  }

  if (bodyEl) {
    bodyEl.textContent =
      overview.preview ||
      "(no body preview)";
  }
  if (badgeEl) badgeEl.style.background = color;
}


function renderDetailFromMessage(overview, msg) {
  const placeholder = document.getElementById("detail-placeholder");
  const detail = document.getElementById("email-detail");
  if (!placeholder || !detail) return;

  placeholder.classList.add("hidden");
  detail.classList.remove("hidden");

  const subjectEl = document.getElementById("detail-subject");
  const fromEl = document.getElementById("detail-from");
  const toEl = document.getElementById("detail-to");
  const dtEl = document.getElementById("detail-datetime");
  const accountEl = document.getElementById("detail-account");
  const bodyEl = document.getElementById("detail-body");
  const badgeEl = document.getElementById("detail-color-badge");

  const subj = msg.subject || (overview && overview.subject) || "(no subject)";

  const fromObj = msg.from_email || (overview && overview.from_email) || {};
  const fromAddr =
    fromObj.name ||
    fromObj.email ||
    "(unknown sender)";

  const toList = msg.to || (overview && overview.to) || [];
  const toAddr = formatAddressList(toList);

  const dateVal = msg.date || (overview && overview.date);
  const dateVerbose = formatDate(dateVal, true);

  let bodyText = msg.text || "";
  if (!bodyText && msg.html) {
    // crude HTML -> text fallback
    bodyText = msg.html.replace(/<[^>]+>/g, "");
  }
  if (!bodyText && overview) {
    bodyText = overview.preview || "(no body)";
  }
  if (!bodyText) {
    bodyText = "(no body)";
  }

  const color = getColorForEmail(overview || msg);

  if (subjectEl) subjectEl.textContent = subj;
  if (fromEl) fromEl.textContent = `From: ${fromAddr}`;
  if (toEl) toEl.textContent = toAddr ? `To: ${toAddr}` : "";
  if (dtEl) dtEl.textContent = `Date: ${dateVerbose}`;

  const ref = (msg && msg.ref) || (overview && overview.ref) || {};
  if (accountEl) {
    const account = ref.account || (overview && overview.account) || "unknown";
    const mailbox = ref.mailbox || (overview && overview.mailbox) || state.currentMailbox;
    accountEl.textContent = `Account: ${account} • Mailbox: ${mailbox}`;
  }

  if (bodyEl) bodyEl.textContent = bodyText;
  if (badgeEl) badgeEl.style.background = color;
}


/* ------------------ Mailbox list rendering ------------------ */

function renderMailboxList(mailboxData) {
  // mailboxData: { accountName: [mb1, mb2, ...] }
  const listEl = document.getElementById("mailbox-list");
  if (!listEl) return;

  listEl.innerHTML = "";

  const entries = Object.entries(mailboxData || {});
  if (!entries.length) {
    listEl.textContent = "No mailboxes available.";
    return;
  }

  for (const [account, mailboxes] of entries) {
    const accTitle = document.createElement("div");
    accTitle.className = "mailbox-account";
    accTitle.textContent = account;
    listEl.appendChild(accTitle);

    for (const m of mailboxes || []) {
      const item = document.createElement("div");
      item.className = "mailbox-item";
      item.dataset.mailbox = m;

      const dot = document.createElement("span");
      dot.className = "mailbox-dot";

      const label = document.createElement("span");
      label.textContent = m;

      item.appendChild(dot);
      item.appendChild(label);

      if (m === state.currentMailbox) {
        item.classList.add("active");
      }

      item.addEventListener("click", () => {
        state.currentMailbox = m;
        state.selectedId = null;
        state.selectedOverview = null;
        updateMailboxLabels();
        highlightMailboxSelection();
        fetchOverview();
      });

      listEl.appendChild(item);
    }
  }

  highlightMailboxSelection();
}

function highlightMailboxSelection() {
  const listEl = document.getElementById("mailbox-list");
  if (!listEl) return;
  const items = listEl.querySelectorAll(".mailbox-item");
  items.forEach((item) => {
    const mb = item.dataset.mailbox;
    if (mb === state.currentMailbox) {
      item.classList.add("active");
    } else {
      item.classList.remove("active");
    }
  });
}

/* ------------------ Labels ------------------ */

function setTotalCountLabel() {
  const el = document.getElementById("total-count");
  if (!el) return;
  el.textContent = String(state.filteredEmails.length || 0);
}

function setCurrentFilterLabel() {
  const el = document.getElementById("current-filter");
  if (!el) return;

  if (!state.filterSenderKey && !state.searchText) {
    el.textContent = "All senders";
  } else if (state.filterSenderKey && !state.searchText) {
    el.textContent = `Sender: ${state.filterSenderKey}`;
  } else if (!state.filterSenderKey && state.searchText) {
    el.textContent = `Search: “${state.searchText}”`;
  } else {
    el.textContent = `Sender: ${state.filterSenderKey}, search: “${state.searchText}”`;
  }
}

function updateMailboxLabels() {
  const headerName = document.getElementById("mailbox-name");
  const folderLabel = document.getElementById("folder-label");
  if (headerName) headerName.textContent = state.currentMailbox;
  if (folderLabel) folderLabel.textContent = state.currentMailbox;
}

/* ------------------ Legend ------------------ */

function buildLegend() {
  const legendEl = document.getElementById("legend-list");
  if (!legendEl) return;

  legendEl.innerHTML = "";

  const counts = {};
  for (const email of state.emails) {
    const key = getSenderKey(email);
    counts[key] = (counts[key] || 0) + 1;
  }

  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]); // by count desc

  for (const [key, count] of entries) {
    const item = document.createElement("div");
    item.className = "legend-item";
    item.dataset.key = key;

    const color = state.colorMap[key] || "#9ca3af";

    item.innerHTML = `
      <span class="legend-color-dot" style="background: ${color};"></span>
      <span>${escapeHtml(key)}</span>
      <span style="margin-left:auto; color:#9ca3af; font-size:0.75rem;">${count}</span>
    `;

    item.addEventListener("click", () => {
      if (state.filterSenderKey === key) {
        state.filterSenderKey = null; // toggle off
      } else {
        state.filterSenderKey = key;
      }
      state.page = 1;
      applyFiltersAndRender();
      highlightLegendSelection();
    });

    legendEl.appendChild(item);
  }

  highlightLegendSelection();
}

function highlightLegendSelection() {
  const legendEl = document.getElementById("legend-list");
  if (!legendEl) return;
  const items = legendEl.querySelectorAll(".legend-item");
  items.forEach((item) => {
    const key = item.dataset.key;
    if (key && key === state.filterSenderKey) {
      item.classList.add("active");
    } else {
      item.classList.remove("active");
    }
  });
}

/* ------------------ Misc utilities ------------------ */

function renderError(msg) {
  const listEl = document.getElementById("email-list");
  const emptyEl = document.getElementById("list-empty");
  if (listEl) listEl.innerHTML = "";
  if (emptyEl) {
    emptyEl.classList.remove("hidden");
    emptyEl.textContent = msg;
  }
}

function makeSnippet(text, maxLen = 120) {
  const stripped = String(text).replace(/\s+/g, " ").trim();
  if (stripped.length <= maxLen) return stripped;
  return stripped.slice(0, maxLen - 3) + "...";
}

function formatDate(value, verbose = false) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);

  if (verbose) {
    return date.toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  return date.toLocaleString(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
