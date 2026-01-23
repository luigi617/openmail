const state = {
  emails: [],          // EmailOverview[] for current page
  filteredEmails: [],
  selectedId: null,    // uid composite key
  selectedOverview: null,
  selectedMessage: null,
  filterSenderKey: null, // legend filter (account)
  searchText: "",
  pageSize: 50,
  currentPage: 1,
  totalPages: 1,
  nextCursor: null,
  prevCursor: null,
  colorMap: {},        // account -> color
  currentMailbox: "INBOX",
  mailboxData: {},     // account -> [mailbox, ...]
  composerMode: null,  // 'compose' | 'reply' | 'reply_all' | 'forward'
  composerAttachmentsFiles: [],
};

// Shorthands to utils
const formatDate = Utils.formatDate;
const escapeHtml = Utils.escapeHtml;
const formatAddress = Utils.formatAddress;
const formatAddressList = Utils.formatAddressList;

document.addEventListener("DOMContentLoaded", () => {
  const prevPageBtn = document.getElementById("prev-page-btn");
  const nextPageBtn = document.getElementById("next-page-btn");
  const searchInput = document.getElementById("search-input");
  const searchBtn = document.getElementById("search-btn");

  if (prevPageBtn) {
    prevPageBtn.addEventListener("click", () => {
      if (!state.prevCursor) return;
      fetchOverview("prev");
    });
  }

  if (nextPageBtn) {
    nextPageBtn.addEventListener("click", () => {
      if (!state.nextCursor) return;
      fetchOverview("next");
    });
  }

  if (searchBtn && searchInput) {
    const triggerSearch = () => {
      state.searchText = searchInput.value.trim().toLowerCase();
      applyFiltersAndRender();
    };

    searchBtn.addEventListener("click", triggerSearch);
    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        triggerSearch();
      }
    });
  }

  // Initial load
  fetchMailboxes();
  fetchOverview();       // first page, no cursor
  initDetailActions();
  initComposer();
});

/* ------------------ Small wrappers around utils ------------------ */

function findAccountForEmail(email) {
  return Utils.findAccountForEmail(email, state.mailboxData);
}

function buildColorMap() {
  state.colorMap = Utils.buildColorMap(state.emails, state.mailboxData);
}

function getColorForEmail(email) {
  return Utils.getColorForEmail(email, state.mailboxData, state.colorMap);
}

function getEmailId(email) {
  return Utils.getEmailId(email);
}

function getMailboxDisplayName(email) {
  return Utils.getMailboxDisplayName(email);
}

/* ------------------ Detail toolbar / move panel ------------------ */

function initDetailActions() {
  const moveBtn = document.getElementById("btn-move");
  const movePanel = document.getElementById("move-panel");
  const moveCancel = document.getElementById("move-cancel");
  const moveConfirm = document.getElementById("move-confirm");

  if (moveBtn && movePanel) {
    moveBtn.addEventListener("click", () => {
      if (!state.selectedOverview) return;
      populateMoveMailboxSelect();
      movePanel.classList.toggle("hidden");
    });
  }

  if (moveCancel && movePanel) {
    moveCancel.addEventListener("click", () => {
      movePanel.classList.add("hidden");
    });
  }

  if (moveConfirm && movePanel) {
    moveConfirm.addEventListener("click", () => {
      const select = document.getElementById("move-mailbox-select");
      if (!select || !state.selectedOverview) return;
      const targetMailbox = select.value;

      // TODO: wire move when backend endpoint exists
      console.log("Move email to mailbox:", targetMailbox, state.selectedOverview);

      movePanel.classList.add("hidden");
    });
  }

  const archiveBtn = document.getElementById("btn-archive");
  const deleteBtn = document.getElementById("btn-delete");
  const replyBtn = document.getElementById("btn-reply");
  const replyAllBtn = document.getElementById("btn-reply-all");
  const forwardBtn = document.getElementById("btn-forward");

  if (archiveBtn) {
    archiveBtn.addEventListener("click", () => {
      archiveSelectedEmail();
    });
  }

  if (deleteBtn) {
    deleteBtn.addEventListener("click", () => {
      deleteSelectedEmail();
    });
  }

  if (replyBtn) {
    replyBtn.addEventListener("click", () => {
      if (!state.selectedOverview) return;
      openComposer("reply");
    });
  }

  if (replyAllBtn) {
    replyAllBtn.addEventListener("click", () => {
      if (!state.selectedOverview) return;
      openComposer("reply_all");
    });
  }

  if (forwardBtn) {
    forwardBtn.addEventListener("click", () => {
      if (!state.selectedOverview) return;
      openComposer("forward");
    });
  }
}

function populateMoveMailboxSelect() {
  const select = document.getElementById("move-mailbox-select");
  if (!select || !state.selectedOverview) return;

  const email = state.selectedOverview;
  const accountKey = findAccountForEmail(email);
  const mailboxes = state.mailboxData[accountKey] || [];

  select.innerHTML = "";

  for (const mb of mailboxes) {
    const opt = document.createElement("option");
    opt.value = mb;
    opt.textContent = getMailboxDisplayName(mb);
    if (mb === state.currentMailbox) {
      opt.selected = true;
    }
    select.appendChild(opt);
  }
}

/* ------------------ Composer (floating box) ------------------ */

function initComposer() {
  const composeBtn = document.getElementById("compose-btn");
  const closeBtn = document.getElementById("composer-close");
  const sendBtn = document.getElementById("composer-send");

  const extraToggle = document.getElementById("composer-extra-toggle");
  const extraMenu = document.getElementById("composer-extra-menu");

  const sendLaterToggle = document.getElementById("composer-send-later-toggle");
  const sendLaterMenu = document.getElementById("composer-send-later-menu");

  const attachBtn = document.getElementById("composer-attach");
  const attachInput = document.getElementById("composer-attachment-input");

  const resizeZone = document.getElementById("composer-resize-zone");
  const composerEl = document.getElementById("composer");

  const composerMain = document.querySelector("#composer .composer-main");
  const attachmentsBar = document.getElementById("composer-attachments");
  if (composerMain && attachmentsBar && attachmentsBar.parentElement !== composerMain) {
    composerMain.appendChild(attachmentsBar);
  }

  if (composeBtn) {
    composeBtn.addEventListener("click", () => openComposer("compose"));
  }

  if (closeBtn) {
    closeBtn.addEventListener("click", () => closeComposer());
  }

  if (sendBtn) {
    sendBtn.addEventListener("click", () => {
      sendCurrentComposer();
    });
  }

  // Extra fields (Cc/Bcc/Reply-To/Priority)
  // Extra fields (Cc/Bcc/Reply-To/Priority) – checkbox popup
  if (extraToggle && extraMenu) {
    const syncExtraMenuFromRows = () => {
      const checkboxes = extraMenu.querySelectorAll(
        'input[type="checkbox"][data-field]'
      );
      checkboxes.forEach((cb) => {
        const field = cb.getAttribute("data-field");
        const row = document.querySelector(
          `.composer-row-extra[data-field="${field}"]`
        );
        // checked if row is currently visible
        cb.checked = !!(row && !row.classList.contains("hidden"));
      });
    };

    extraToggle.addEventListener("click", (ev) => {
      ev.stopPropagation();
      syncExtraMenuFromRows();
      extraMenu.classList.toggle("hidden");
    });

    // When a checkbox is changed, show/hide the corresponding row
    extraMenu.addEventListener("change", (ev) => {
      const cb = ev.target.closest('input[type="checkbox"][data-field]');
      if (!cb) return;
      const field = cb.getAttribute("data-field");
      const row = document.querySelector(
        `.composer-row-extra[data-field="${field}"]`
      );
      if (!row) return;

      if (cb.checked) {
        row.classList.remove("hidden");
      } else {
        row.classList.add("hidden");
      }
    });

    // click outside closes the popup
    document.addEventListener("click", (ev) => {
      if (extraMenu.classList.contains("hidden")) return;
      const inside =
        ev.target.closest("#composer-extra-menu") ||
        ev.target.closest("#composer-extra-toggle");
      if (!inside) extraMenu.classList.add("hidden");
    });
  }


  // Send later popup
  if (sendLaterToggle && sendLaterMenu) {
    sendLaterToggle.addEventListener("click", (ev) => {
      ev.stopPropagation();
      sendLaterMenu.classList.toggle("hidden");
    });

    sendLaterMenu.addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-delay]");
      if (!btn) return;
      const label = btn.textContent.trim();
      sendLaterMenu.classList.add("hidden");
      // UI only for now – backend scheduling not implemented
      alert(`"Send later" (${label}) is not wired to the backend yet.`);
    });

    document.addEventListener("click", (ev) => {
      if (sendLaterMenu.classList.contains("hidden")) return;
      const inside =
        ev.target.closest("#composer-send-later-menu") ||
        ev.target.closest("#composer-send-later-toggle");
      if (!inside) sendLaterMenu.classList.add("hidden");
    });
  }

  // Attachments: open file dialog and render pills
  if (attachBtn && attachInput) {
    attachBtn.addEventListener("click", () => {
      attachInput.click();
    });

    attachInput.addEventListener("change", () => {
      state.composerAttachmentsFiles = Array.from(attachInput.files || []);
      renderComposerAttachments();
    });
  }

  // Resize by dragging the top-right handle
  if (resizeZone && composerEl) {
    let isResizing = false;
    let startX = 0;
    let startY = 0;
    let startWidth = 0;
    let startHeight = 0;
    const minWidth = 420;
    const minHeight = 260;

    const onMouseMove = (e) => {
      if (!isResizing) return;
      // drag top-left: moving left/up grows the window
      const dx = startX - e.clientX;
      const dy = startY - e.clientY;

      const newWidth = Math.max(minWidth, startWidth + dx);
      const newHeight = Math.max(minHeight, startHeight + dy);

      composerEl.style.width = newWidth + "px";
      composerEl.style.height = newHeight + "px";
    };

    const onMouseUp = () => {
      if (!isResizing) return;
      isResizing = false;
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    };

    resizeZone.addEventListener("mousedown", (e) => {
      e.preventDefault();
      isResizing = true;

      const rect = composerEl.getBoundingClientRect();
      startX = e.clientX;
      startY = e.clientY;
      startWidth = rect.width;
      startHeight = rect.height;

      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    });
  }
}

function openComposer(mode) {
  const composer = document.getElementById("composer");
  const titleEl = document.getElementById("composer-title");
  const toInput = document.getElementById("composer-to");
  const subjInput = document.getElementById("composer-subject");
  const bodyInput = document.getElementById("composer-body");
  const attachmentInput = document.getElementById("composer-attachment-input");
  const extraRows = document.querySelectorAll(".composer-row-extra");
  const extraMenu = document.getElementById("composer-extra-menu");
  const sendLaterMenu = document.getElementById("composer-send-later-menu");

  if (!composer || !titleEl || !toInput || !subjInput || !bodyInput) return;

  // reset extra fields and menus
  // if (extraRows && extraRows.length) {
  //   extraRows.forEach((row) => row.classList.add("hidden"));
  // }
  if (extraMenu) extraMenu.classList.add("hidden");
  if (sendLaterMenu) sendLaterMenu.classList.add("hidden");

  // reset attachments
  state.composerAttachmentsFiles = [];
  if (attachmentInput) attachmentInput.value = "";
  renderComposerAttachments();

  state.composerMode = mode || "compose";
  composer.classList.remove("hidden");

  let subj = "";
  let toStr = "";
  let body = "";

  const ov = state.selectedOverview;
  const msg = state.selectedMessage;
  const originalSubj = (msg && msg.subject) || (ov && ov.subject) || "";

  if (mode === "compose") {
    titleEl.textContent = "New message";
  } else if (mode === "reply") {
    titleEl.textContent = "Reply";
    const fromObj = (msg && msg.from_email) || (ov && ov.from_email) || {};
    if (fromObj.email || fromObj.name) {
      toStr = formatAddress(fromObj);
    }
    subj =
      originalSubj && originalSubj.toLowerCase().startsWith("re:")
        ? originalSubj
        : originalSubj
        ? `Re: ${originalSubj}`
        : "";
  } else if (mode === "reply_all") {
    titleEl.textContent = "Reply all";
    const fromObj = (msg && msg.from_email) || (ov && ov.from_email) || {};
    const toList = (msg && msg.to) || (ov && ov.to) || [];
    const ccList = (msg && msg.cc) || [];
    const allRecipients = [];
    if (fromObj && (fromObj.email || fromObj.name)) {
      allRecipients.push(fromObj);
    }
    allRecipients.push(...toList, ...ccList);
    toStr = formatAddressList(allRecipients);
    subj =
      originalSubj && originalSubj.toLowerCase().startsWith("re:")
        ? originalSubj
        : originalSubj
        ? `Re: ${originalSubj}`
        : "";
  } else if (mode === "forward") {
    titleEl.textContent = "Forward";
    subj =
      originalSubj && originalSubj.toLowerCase().startsWith("fwd:")
        ? originalSubj
        : originalSubj
        ? `Fwd: ${originalSubj}`
        : "";
  } else {
    titleEl.textContent = "Message";
  }

  toInput.value = toStr;
  subjInput.value = subj;
  bodyInput.value = body;
  bodyInput.focus();
}

function renderComposerAttachments() {
  const container = document.getElementById("composer-attachments");
  if (!container) return;

  const files = state.composerAttachmentsFiles || [];

  if (!files.length) {
    container.classList.add("hidden");
    container.innerHTML = "";
    return;
  }

  container.classList.remove("hidden");
  container.innerHTML = "";

  files.forEach((file, index) => {
    const pill = document.createElement("div");
    pill.className = "attachment-pill";

    // filename
    const nameSpan = document.createElement("span");
    nameSpan.className = "attachment-pill-name";
    nameSpan.textContent = file.name;

    const actions = document.createElement("div");
    actions.className = "attachment-pill-actions";

    // 🔽 Download button with SVG icon
    const downloadBtn = document.createElement("button");
    downloadBtn.type = "button";
    downloadBtn.className = "attachment-pill-btn attachment-pill-icon";
    downloadBtn.title = "Download";

    const downloadIcon = document.createElement("img");
    downloadIcon.src = "/static/svg/download.svg"; // same dir as other svgs
    downloadIcon.alt = "";
    downloadIcon.className = "icon-img";

    downloadBtn.appendChild(downloadIcon);

    downloadBtn.addEventListener("click", (e) => {
      // don't trigger card preview
      e.stopPropagation();
      const url = URL.createObjectURL(file);
      const a = document.createElement("a");
      a.href = url;
      a.download = file.name || "attachment";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    });

    // remove (X)
    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.textContent = "×";
    removeBtn.className =
      "attachment-pill-btn attachment-pill-remove";
    removeBtn.title = "Remove attachment";

    removeBtn.addEventListener("click", (e) => {
      // don't trigger card preview
      e.stopPropagation();
      const current = state.composerAttachmentsFiles || [];
      current.splice(index, 1);
      state.composerAttachmentsFiles = current;
      renderComposerAttachments();
    });

    actions.appendChild(downloadBtn);
    actions.appendChild(removeBtn);

    pill.appendChild(nameSpan);
    pill.appendChild(actions);

    // 🔽 Click the card itself to preview in a new tab
    pill.addEventListener("click", () => {
      const url = URL.createObjectURL(file);
      window.open(url, "_blank");
    });

    container.appendChild(pill);
  });
}

function closeComposer() {
  const composer = document.getElementById("composer");
  if (!composer) return;
  composer.classList.add("hidden");
  state.composerMode = null;
}

async function sendCurrentComposer() {
  const mode = state.composerMode;
  const toInput = document.getElementById("composer-to");
  const subjInput = document.getElementById("composer-subject");
  const bodyInput = document.getElementById("composer-body");
  const sendBtn = document.getElementById("composer-send");

  if (!mode || !toInput || !subjInput || !bodyInput || !sendBtn) return;

  if (mode === "compose") {
    // No generic compose/send API is defined in the provided backend.
    alert("Compose/send is not wired to a backend endpoint yet.");
    return;
  }

  const ref = getSelectedRef();
  if (!ref) {
    alert("No email selected.");
    return;
  }

  const { account, mailbox, uid } = ref;
  const bodyText = bodyInput.value || "";

  try {
    sendBtn.disabled = true;

    if (mode === "reply") {
      await Api.replyEmail({
        account,
        mailbox,
        uid,
        body: bodyText,
        bodyHtml: null,
        fromAddr: null,
        quoteOriginal: true,
      });
    } else if (mode === "reply_all") {
      await Api.replyAllEmail({
        account,
        mailbox,
        uid,
        body: bodyText,
        bodyHtml: null,
        fromAddr: null,
        quoteOriginal: true,
      });
    } else if (mode === "forward") {
      const rawTo = (toInput.value || "").trim();
      if (!rawTo) {
        alert("Please specify at least one recipient.");
        return;
      }
      const toList = rawTo
        .split(/[;,]/)
        .map((s) => s.trim())
        .filter(Boolean);

      await Api.forwardEmail({
        account,
        mailbox,
        uid,
        to: toList,
        body: bodyText || null,
        bodyHtml: null,
        fromAddr: null,
        includeAttachments: true,
      });
    } else {
      alert("Unknown composer mode.");
      return;
    }

    closeComposer();
    alert("Message sent.");
  } catch (err) {
    console.error("Error sending:", err);
    alert("Failed to send message.");
  } finally {
    sendBtn.disabled = false;
  }
}

/* ------------------ Archive / Delete helpers ------------------ */

async function archiveSelectedEmail() {
  const ref = getSelectedRef();
  if (!ref) {
    alert("No email selected.");
    return;
  }
  const { account, mailbox, uid } = ref;

  if (!confirm("Archive this email?")) return;

  try {
    await Api.archiveEmail({ account, mailbox, uid });
    state.currentPage = 1;
    fetchOverview();
  } catch (err) {
    console.error("Error archiving:", err);
    alert("Error archiving email.");
  }
}

async function deleteSelectedEmail() {
  const ref = getSelectedRef();
  if (!ref) {
    alert("No email selected.");
    return;
  }
  const { account, mailbox, uid } = ref;

  if (!confirm("Permanently delete this email?")) return;

  try {
    await Api.deleteEmail({ account, mailbox, uid });
    state.currentPage = 1;
    fetchOverview();
  } catch (err) {
    console.error("Error deleting:", err);
    alert("Error deleting email.");
  }
}

/* ------------------ API calls ------------------ */

async function fetchMailboxes() {
  try {
    const data = await Api.getMailboxes(); // { account: [mb1, ...] }
    state.mailboxData = data || {};
    renderMailboxList(data);
  } catch (err) {
    console.error("Error fetching mailboxes:", err);
  }
}

/**
 * Fetch a page of overview data from backend.
 * direction: null | "next" | "prev"
 * uses cursor-based pagination from meta.next_cursor / meta.prev_cursor
 */
async function fetchOverview(direction = null) {
  try {
    const args = {
      mailbox: state.currentMailbox,
      limit: state.pageSize,
    };

    if (direction === "next" && state.nextCursor) {
      args.cursor = state.nextCursor;
    } else if (direction === "prev" && state.prevCursor) {
      args.cursor = state.prevCursor;
    }

    const payload = await Api.getOverview(args);
    const list = Array.isArray(payload.data) ? payload.data : [];
    const meta = payload.meta || {};

    state.emails = list;
    state.selectedId = null;
    state.selectedOverview = null;
    state.selectedMessage = null;

    state.nextCursor = meta.next_cursor || null;
    state.prevCursor = meta.prev_cursor || null;

    const totalCount =
      typeof meta.total_count === "number" ? meta.total_count : null;

    if (!direction || !state.currentPage) {
      state.currentPage = 1;
    } else if (direction === "next") {
      state.currentPage += 1;
    } else if (direction === "prev") {
      state.currentPage = Math.max(1, state.currentPage - 1);
    }

    if (totalCount != null && state.pageSize > 0) {
      state.totalPages = Math.max(
        1,
        Math.ceil(totalCount / state.pageSize)
      );
    } else {
      state.totalPages = state.currentPage || 1;
    }

    buildColorMap();
    buildLegend();
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
  const mailbox = ref.mailbox || overview.mailbox || state.currentMailbox;
  const uid = ref.uid;

  if (!account || !mailbox || uid == null) {
    renderDetailFromOverviewOnly(overview);
    return;
  }

  try {
    state.selectedMessage = null;
    const msg = await Api.getEmail({ account, mailbox, uid });
    state.selectedMessage = msg;
    renderDetailFromMessage(overview, msg);
  } catch (err) {
    console.error("Error fetching email detail:", err);
    renderDetailFromOverviewOnly(overview);
  }
}

/* ------------------ State utilities ------------------ */

function getSelectedRef() {
  const ov = state.selectedOverview;
  if (!ov) return null;
  const ref = ov.ref || {};
  const account = ref.account || ov.account;
  const mailbox = ref.mailbox || ov.mailbox || state.currentMailbox;
  const uid = ref.uid;

  if (!account || uid == null) return null;
  return { account, mailbox, uid };
}

/* ------------------ Filtering & rendering ------------------ */

function applyFiltersAndRender() {
  let filtered = [...state.emails];

  if (state.filterSenderKey) {
    filtered = filtered.filter(
      (e) => findAccountForEmail(e) === state.filterSenderKey
    );
  }

  if (state.searchText) {
    filtered = filtered.filter((e) => {
      const subject = (e.subject || "").toLowerCase();
      const snippet = (e.snippet || "").toLowerCase();
      return (
        subject.includes(state.searchText) ||
        snippet.includes(state.searchText)
      );
    });
  }

  state.filteredEmails = filtered;
  renderListAndPagination();
}

function renderListAndPagination() {
  const listEl = document.getElementById("email-list");
  const emptyEl = document.getElementById("list-empty");
  const pageInfoEl = document.getElementById("page-info");
  const prevBtn = document.getElementById("prev-page-btn");
  const nextBtn = document.getElementById("next-page-btn");

  if (!listEl || !emptyEl || !pageInfoEl) return;

  const total = state.filteredEmails.length;
  listEl.innerHTML = "";

  if (!total) {
    emptyEl.classList.remove("hidden");
  } else {
    emptyEl.classList.add("hidden");
  }

  for (const email of state.filteredEmails) {
    const card = document.createElement("div");
    card.className = "email-card";

    const ref = email.ref || {};
    const emailId = getEmailId(email);

    card.dataset.uid = ref.uid != null ? ref.uid : "";
    card.dataset.account = ref.account || email.account || "";
    card.dataset.mailbox = ref.mailbox || email.mailbox || "";

    if (emailId && emailId === state.selectedId) {
      card.classList.add("selected");
    }

    const color = getColorForEmail(email);
    const fromObj = email.from_email || {};
    const fromAddr =
      fromObj.name ||
      fromObj.email ||
      "(unknown sender)";
    const dateStr = formatDate(email.date);
    const subj = email.subject || "(no subject)";

    card.innerHTML = `
      <div class="email-color-strip" style="background: ${color};"></div>
      <div class="email-main">
        <div class="email-row-top">
          <div class="email-from">${escapeHtml(fromAddr)}</div>
          <div class="email-date">${escapeHtml(dateStr)}</div>
        </div>
        <div class="email-subject">${escapeHtml(subj)}</div>
      </div>
    `;

    card.addEventListener("click", () => {
      state.selectedId = getEmailId(email);
      state.selectedOverview = email;
      state.selectedMessage = null;
      renderListAndPagination(); // refresh selected state
      fetchEmailDetail(email);   // get full message from backend
    });

    listEl.appendChild(card);
  }

  let pageText = `Page ${state.currentPage || 1}`;
  if (state.totalPages) {
    pageText += ` / ${state.totalPages}`;
  }
  pageInfoEl.textContent = pageText;

  if (prevBtn) prevBtn.disabled = !state.prevCursor;
  if (nextBtn) nextBtn.disabled = !state.nextCursor;
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
}

/**
 * Overview-only fallback (no full message)
 */
function renderDetailFromOverviewOnly(overview) {
  const placeholder = document.getElementById("detail-placeholder");
  const detail = document.getElementById("email-detail");
  const bodyHtmlEl = document.getElementById("detail-body-html");
  const bodyTextEl = document.getElementById("detail-body-text");
  const subjectEl = document.getElementById("detail-subject");
  const fromEl = document.getElementById("detail-from");
  const toEl = document.getElementById("detail-to");
  const dtEl = document.getElementById("detail-datetime");
  const accountEl = document.getElementById("detail-account");
  const badgeEl = document.getElementById("detail-color-badge");

  if (!placeholder || !detail || !overview) return;

  placeholder.classList.add("hidden");
  detail.classList.remove("hidden");

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
    accountEl.textContent = `Account: ${account} • Mailbox: ${getMailboxDisplayName(mailbox)}`;
  }

  if (badgeEl) badgeEl.style.background = color;

  if (bodyHtmlEl) {
    bodyHtmlEl.classList.add("hidden");
    bodyHtmlEl.innerHTML = "";
  }
}

/**
 * Full message rendering: support both html + text
 */
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
  const bodyHtmlEl = document.getElementById("detail-body-html");
  const bodyTextEl = document.getElementById("detail-body-text");
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
  const color = getColorForEmail(overview || msg);

  if (subjectEl) subjectEl.textContent = subj;
  if (fromEl) fromEl.textContent = `From: ${fromAddr}`;
  if (toEl) toEl.textContent = toAddr ? `To: ${toAddr}` : "";
  if (dtEl) dtEl.textContent = `Date: ${dateVerbose}`;

  const ref = (msg && msg.ref) || (overview && overview.ref) || {};
  if (accountEl) {
    const account = ref.account || (overview && overview.account) || "unknown";
    const mailbox = ref.mailbox || (overview && overview.mailbox) || state.currentMailbox;
    accountEl.textContent = `Account: ${account} • Mailbox: ${getMailboxDisplayName(mailbox)}`;
  }

  if (badgeEl) badgeEl.style.background = color;

  let textBody = msg.text || "";
  if (!textBody && msg.html) {
    textBody = msg.html.replace(/<[^>]+>/g, "");
  }
  if (!textBody && overview) {
    textBody = "";
  }

  const htmlBody = msg.html || "";

  if (htmlBody && bodyHtmlEl) {
    // Show HTML body, hide plain text
    bodyHtmlEl.classList.remove("hidden");
    if (bodyTextEl) {
      bodyTextEl.classList.add("hidden");
      bodyTextEl.textContent = "";
    }

    // Create a shadow root once and reuse it
    if (!bodyHtmlEl._shadowRoot && bodyHtmlEl.attachShadow) {
      bodyHtmlEl._shadowRoot = bodyHtmlEl.attachShadow({ mode: "open" });
    }

    if (bodyHtmlEl._shadowRoot) {
      // Optional: add a minimal baseline style for readability inside the email
      bodyHtmlEl._shadowRoot.innerHTML = `
        <style>
          /* Baseline inside the email bubble only */
          :host {
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            font-size: 0.88rem;
          }
          body {
            margin: 0;
          }
        </style>
        ${htmlBody}
      `;
    } else {
      // Fallback for very old browsers – behaves like before
      bodyHtmlEl.innerHTML = htmlBody;
    }
  } else if (textBody && bodyTextEl) {
    // No HTML: show text, hide HTML
    bodyTextEl.classList.remove("hidden");
    bodyTextEl.textContent = textBody;

    if (bodyHtmlEl) {
      bodyHtmlEl.classList.add("hidden");
      bodyHtmlEl.innerHTML = "";
    }
  } else {
    // No body at all → simple fallback
    if (bodyHtmlEl) {
      bodyHtmlEl.classList.add("hidden");
      bodyHtmlEl.innerHTML = "";
    }
    if (bodyTextEl) {
      bodyTextEl.classList.remove("hidden");
      bodyTextEl.textContent = "(no body)";
    }
  }
}

/* ------------------ Mailbox list rendering ------------------ */

function renderMailboxList(mailboxData) {
  const listEl = document.getElementById("mailbox-list");
  if (!listEl) return;

  listEl.innerHTML = "";

  const entries = Object.entries(mailboxData || {});
  if (!entries.length) {
    listEl.textContent = "No mailboxes available.";
    return;
  }

  for (const [account, mailboxes] of entries) {
    const group = document.createElement("div");
    group.className = "mailbox-group";

    const accHeader = document.createElement("button");
    accHeader.type = "button";
    accHeader.className = "mailbox-account";
    accHeader.innerHTML = `
      <span class="mailbox-account-chev">▾</span>
      <span>${escapeHtml(account)}</span>
    `;

    const mbContainer = document.createElement("div");
    mbContainer.className = "mailbox-group-items";

    for (const m of mailboxes || []) {
      const item = document.createElement("div");
      item.className = "mailbox-item";
      item.dataset.mailbox = m;

      const dot = document.createElement("span");
      dot.className = "mailbox-dot";

      const label = document.createElement("span");
      label.textContent = getMailboxDisplayName(m);

      item.appendChild(dot);
      item.appendChild(label);

      if (m === state.currentMailbox) {
        item.classList.add("active");
      }

      item.addEventListener("click", () => {
        state.currentMailbox = m;
        state.selectedId = null;
        state.selectedOverview = null;
        state.selectedMessage = null;
        state.currentPage = 1;
        highlightMailboxSelection();
        fetchOverview(); // restart pagination from first page for selected mailbox
      });

      mbContainer.appendChild(item);
    }

    accHeader.addEventListener("click", () => {
      const isCollapsed = mbContainer.classList.toggle("collapsed");
      accHeader.classList.toggle("collapsed", isCollapsed);
    });

    group.appendChild(accHeader);
    group.appendChild(mbContainer);
    listEl.appendChild(group);
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

/* ------------------ Legend ------------------ */

function buildLegend() {
  const legendEl = document.getElementById("legend-list");
  if (!legendEl) return;

  legendEl.innerHTML = "";

  const mailboxAccounts = Object.keys(state.mailboxData || {});
  const counts = {};

  for (const account of mailboxAccounts) {
    counts[account] = 0;
  }

  for (const email of state.emails) {
    const key = findAccountForEmail(email);
    if (key in counts) {
      counts[key] = (counts[key] || 0) + 1;
    }
  }

  const entries = Object.entries(counts).sort((a, b) => {
    if (b[1] !== a[1]) return b[1] - a[1];
    return a[0].localeCompare(b[0]);
  });

  for (const [accountEmail] of entries) {
    const item = document.createElement("div");
    item.className = "legend-item";
    item.dataset.key = accountEmail;

    const color = state.colorMap[accountEmail] || "#9ca3af";

    item.innerHTML = `
      <span class="legend-color-dot" style="background: ${color};"></span>
      <span>${escapeHtml(accountEmail)}</span>
    `;

    item.addEventListener("click", () => {
      if (state.filterSenderKey === accountEmail) {
        state.filterSenderKey = null;
      } else {
        state.filterSenderKey = accountEmail;
      }
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



