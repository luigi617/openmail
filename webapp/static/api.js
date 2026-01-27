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

    async replyEmail({
      account,
      mailbox,
      uid,
      body,
      bodyHtml,
      fromAddr,
      quoteOriginal,
      to,
      cc,
      bcc,
      subject,
      replyTo,
      priority,
      attachments,
    }) {
      const url = buildEmailUrl(account, mailbox, uid, "/reply");
      const form = new FormData();

      form.append("body", body || "");
      if (bodyHtml) form.append("body_html", bodyHtml);
      if (fromAddr) form.append("from_addr", fromAddr);
      form.append("quote_original", quoteOriginal ? "true" : "false");
      if (subject) form.append("subject", subject);

      (to || []).forEach((addr) => form.append("to", addr));
      (cc || []).forEach((addr) => form.append("cc", addr));
      (bcc || []).forEach((addr) => form.append("bcc", addr));
      (replyTo || []).forEach((addr) => form.append("reply_to", addr));
      if (priority) form.append("priority", priority);

      (attachments || []).forEach((file) => {
        form.append("attachments", file);
      });

      return getJSON(url, {
        method: "POST",
        body: form,
      });
    },

        async replyAllEmail({
      account,
      mailbox,
      uid,
      body,
      bodyHtml,
      fromAddr,
      quoteOriginal,
      to,
      cc,
      bcc,
      subject,
      replyTo,
      priority,
      attachments,
    }) {
      const url = buildEmailUrl(account, mailbox, uid, "/reply-all");
      const form = new FormData();

      form.append("body", body || "");
      if (bodyHtml) form.append("body_html", bodyHtml);
      if (fromAddr) form.append("from_addr", fromAddr);
      form.append("quote_original", quoteOriginal ? "true" : "false");
      if (subject) form.append("subject", subject);

      (to || []).forEach((addr) => form.append("to", addr));
      (cc || []).forEach((addr) => form.append("cc", addr));
      (bcc || []).forEach((addr) => form.append("bcc", addr));
      (replyTo || []).forEach((addr) => form.append("reply_to", addr));
      if (priority) form.append("priority", priority);

      (attachments || []).forEach((file) => {
        form.append("attachments", file);
      });

      return getJSON(url, {
        method: "POST",
        body: form,
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
      includeOriginal,
      includeAttachments,
      cc,
      bcc,
      subject,
      replyTo,
      priority,
      attachments,
    }) {
      const url = buildEmailUrl(account, mailbox, uid, "/forward");
      const form = new FormData();

      (to || []).forEach((addr) => form.append("to", addr));
      if (body != null) form.append("body", body);
      if (bodyHtml) form.append("body_html", bodyHtml);
      if (fromAddr) form.append("from_addr", fromAddr);
      form.append("include_original", includeOriginal ? "true" : "false");
      form.append("include_attachments", includeAttachments !== false ? "true" : "false");
      if (subject) form.append("subject", subject);

      (cc || []).forEach((addr) => form.append("cc", addr));
      (bcc || []).forEach((addr) => form.append("bcc", addr));
      (replyTo || []).forEach((addr) => form.append("reply_to", addr));
      if (priority) form.append("priority", priority);

      (attachments || []).forEach((file) => {
        form.append("attachments", file);
      });

      return getJSON(url, {
        method: "POST",
        body: form,
      });
    },

    async sendEmail({
      account,
      subject,
      to,
      fromAddr,
      cc,
      bcc,
      text,
      html,
      replyTo,
      priority,
      attachments,
    }) {
      const a = encodeURIComponent(account);
      const url = `/api/accounts/${a}/send`;
      const form = new FormData();

      form.append("subject", subject || "");
      (to || []).forEach((addr) => form.append("to", addr));
      if (fromAddr) form.append("from_addr", fromAddr);
      (cc || []).forEach((addr) => form.append("cc", addr));
      (bcc || []).forEach((addr) => form.append("bcc", addr));
      if (text != null) form.append("text", text);
      if (html) form.append("html", html);
      (replyTo || []).forEach((addr) => form.append("reply_to", addr));
      if (priority) form.append("priority", priority);

      (attachments || []).forEach((file) => {
        form.append("attachments", file);
      });

      return getJSON(url, {
        method: "POST",
        body: form,
      });
    },


  };

  global.Api = Api;
})(window);
