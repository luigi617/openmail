(function (global) {
  async function getJSON(url, options) {
    const res = await fetch(url, options);
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(
        `Request failed: ${res.status} ${res.statusText}${text ? " - " + text : ""}`
      );
    }
    return res.json();
  }

  function buildEmailUrl(account, mailbox, uid, suffix) {
    const a = encodeURIComponent(account);
    const m = encodeURIComponent(mailbox);
    const u = encodeURIComponent(uid);
    return `/api/accounts/${a}/mailboxes/${m}/emails/${u}${suffix || ""}`;
  }

  const Api = {
    async getMailboxes() {
      return getJSON("/api/emails/mailbox");
    },

    async getOverview({ mailbox, limit, cursor, accounts }) {
      const params = new URLSearchParams();
      if (mailbox) params.set("mailbox", mailbox);
      if (limit != null) params.set("limit", String(limit));
      if (cursor) params.set("cursor", cursor);

      // accounts is a list → repeat "accounts=" in query string
      if (!cursor && Array.isArray(accounts) && accounts.length) {
        for (const acc of accounts) {
          params.append("accounts", acc);
        }
      }

      const qs = params.toString();
      const url = `/api/emails/overview${qs ? "?" + qs : ""}`;
      return getJSON(url);
    },

    async getEmail({ account, mailbox, uid }) {
      const url = buildEmailUrl(account, mailbox, uid, "");
      return getJSON(url);
    },

    async archiveEmail({ account, mailbox, uid }) {
      const url = buildEmailUrl(account, mailbox, uid, "/archive");
      return getJSON(url, { method: "POST" });
    },

    async deleteEmail({ account, mailbox, uid }) {
      const url = buildEmailUrl(account, mailbox, uid, "");
      return getJSON(url, { method: "DELETE" });
    },

    async replyEmail({ account, mailbox, uid, body, bodyHtml, fromAddr, quoteOriginal }) {
      const url = buildEmailUrl(account, mailbox, uid, "/reply");
      const payload = {
        body: body || "",
        body_html: bodyHtml || null,
        from_addr: fromAddr || null,
        quote_original: !!quoteOriginal,
      };
      return getJSON(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    },

    async replyAllEmail({ account, mailbox, uid, body, bodyHtml, fromAddr, quoteOriginal }) {
      const url = buildEmailUrl(account, mailbox, uid, "/reply-all");
      const payload = {
        body: body || "",
        body_html: bodyHtml || null,
        from_addr: fromAddr || null,
        quote_original: !!quoteOriginal,
      };
      return getJSON(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    },

    async forwardEmail({
      account,
      mailbox,
      uid,
      to,
      body,
      bodyHtml,
      fromAddr,
      includeAttachments,
    }) {
      const url = buildEmailUrl(account, mailbox, uid, "/forward");
      const payload = {
        to: to || [],
        body: body || null,
        body_html: bodyHtml || null,
        from_addr: fromAddr || null,
        include_attachments: includeAttachments !== false,
      };
      return getJSON(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    },
  };

  global.Api = Api;
})(window);
