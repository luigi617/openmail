// src/hooks/useComposer.ts
import DOMPurify from "dompurify";
import { useCallback, useMemo, useState } from "react";
import { EmailApi } from "../api/emailApi";
import type { ComposerExtraFieldKey, ComposerMode, ComposerState } from "../types/composer";
import type { Priority } from "../types/shared";
import type { MailboxData, EmailOverview, EmailMessage } from "../types/email";
import type { EmailRef } from "../types/shared";
import { buildForwardedOriginalBodyHtml, buildQuotedOriginalBodyHtml } from "../utils/messageBuilders";
import { formatAddress, formatAddressList } from "../utils/emailFormat";

function sanitizeForComposer(html: string) {
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
    FORBID_TAGS: ["style", "script", "link", "meta", "base", "iframe", "object", "embed"],
    FORBID_ATTR: ["onload","onclick","onerror","onmouseover","onfocus","onsubmit"],
  });
}

function splitRawList(raw: string): string[] {
  return (raw || "")
    .split(/[;,]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function stripHtmlToText(html: string): string {
  return html.replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim();
}

function guessDraftsMailbox(mailboxes?: string[]): string | undefined {
  if (!mailboxes?.length) return undefined;
  const lower = mailboxes.map((m) => ({ m, l: m.toLowerCase() }));

  // common variants
  const candidates = [
    "drafts",
    "draft",
    "[gmail]/drafts",
    "inbox/drafts",
    "inbox.drafts",
  ];

  for (const c of candidates) {
    const hit = lower.find((x) => x.l === c);
    if (hit) return hit.m;
  }

  // contains "draft"
  const contains = lower.find((x) => x.l.includes("draft"));
  return contains?.m;
}

// make sure that to, cc, bcc is considered in hasContentNow
function getAddressDraft(fieldId: string): string {
  const el = document.getElementById(fieldId) as HTMLInputElement | null;
  return (el?.value || "").trim();
}

function mergeUniqueCaseInsensitive(a: string[], b: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];

  for (const item of [...a, ...b]) {
    const v = (item || "").trim();
    if (!v) continue;
    const key = v.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(v);
  }

  return out;
}


export function useComposer(args: {
  mailboxData: MailboxData; // account -> mailboxes
  selectedOverview: EmailOverview | null;
  selectedMessage: EmailMessage | null;
  getSelectedRef: () => EmailRef | null;

  showCloseConfirm: (cfg: { onSaveDraft: () => Promise<void>; onDiscard: () => void }) => void;
}) {
  const [state, setState] = useState<ComposerState>(() => ({
    open: false,
    minimized: false,
    mode: "compose",
    extra: { cc: false, bcc: false, replyto: false, priority: false },
    to: [],
    cc: [],
    bcc: [],
    subject: "",
    replyToRaw: "",
    priority: "medium",
    fromAccount: "",
    text: "",
    html: "",
    attachments: [],
    error: "",
  }));

  const accounts = useMemo(() => Object.keys(args.mailboxData || {}), [args.mailboxData]);

  const hasContentNow = useCallback(() => {
    const bodyText = stripHtmlToText(state.html || "");

    const toDraft = getAddressDraft("composer-to");
    const ccDraft = getAddressDraft("composer-cc");
    const bccDraft = getAddressDraft("composer-bcc");
    
    return (
      state.to.length > 0 ||
      state.cc.length > 0 ||
      state.bcc.length > 0 ||
      toDraft.length > 0 ||
      ccDraft.length > 0 ||
      bccDraft.length > 0 ||
      state.subject.trim().length > 0 ||
      state.replyToRaw.trim().length > 0 ||
      bodyText.length > 0 ||
      state.attachments.length > 0
    );
  }, [state]);

  const reset = useCallback(() => {
    setState((s) => ({
      ...s,
      minimized: false,
      mode: "compose",
      extra: { cc: false, bcc: false, replyto: false, priority: false },
      to: [],
      cc: [],
      bcc: [],
      subject: "",
      replyToRaw: "",
      priority: "medium",
      fromAccount: "",
      text: "",
      html: "",
      attachments: [],
      error: "",
    }));
  }, []);

  const close = useCallback(() => {
    setState((s) => ({ ...s, open: false, minimized: false, error: "" }));
  }, []);

  const requestClose = useCallback(() => {
    if (!state.open) return;

    if (!hasContentNow()) {
      reset();
      close();
      return;
    }

    args.showCloseConfirm({
      onSaveDraft: async () => {
        const ok = await saveDraft();
        
        if (ok) {
          reset();
          close();
        }
      },
      onDiscard: () => {
        reset();
        close();
      },
    });
  }, [state.open, state.to, hasContentNow, args, reset, close]);

  const toggleExtraField = useCallback((k: ComposerExtraFieldKey) => {
    setState((s) => ({ ...s, extra: { ...s.extra, [k]: !s.extra[k] } }));
  }, []);

  const setFromAccount = useCallback((v: string) => setState((s) => ({ ...s, fromAccount: v })), []);
  const setPriority = useCallback((v: Priority) => setState((s) => ({ ...s, priority: v })), []);
  const setReplyToRaw = useCallback((v: string) => setState((s) => ({ ...s, replyToRaw: v })), []);
  const setSubject = useCallback((v: string) => setState((s) => ({ ...s, subject: v })), []);
  const setHtml = useCallback((v: string) => setState((s) => ({ ...s, html: v })), []);
  const setTo = useCallback((v: string[]) => setState((s) => ({ ...s, to: v })), []);
  const setCc = useCallback((v: string[]) => setState((s) => ({ ...s, cc: v })), []);
  const setBcc = useCallback((v: string[]) => setState((s) => ({ ...s, bcc: v })), []);
  const setError = useCallback((msg: string) => setState((s) => ({ ...s, error: msg })), []);

  const addAttachments = useCallback((files: File[]) => {
    setState((s) => ({ ...s, attachments: [...s.attachments, ...files] }));
  }, []);

  const removeAttachmentAt = useCallback((idx: number) => {
    setState((s) => {
      const next = s.attachments.slice();
      next.splice(idx, 1);
      return { ...s, attachments: next };
    });
  }, []);

  const open = useCallback(
    (mode: ComposerMode) => {
      const ov = args.selectedOverview;
      const msg = args.selectedMessage;
      const originalSubj = msg?.subject || ov?.subject || "";

      // default From
      let defaultFrom = "";
      if (mode === "reply" || mode === "reply_all" || mode === "forward") {
        defaultFrom = args.getSelectedRef()?.account ?? "";
      } else {
        defaultFrom = accounts[0] ?? "";
      }

      let subject = "";
      let toStr = "";
      let html = "";

      if (mode === "compose") {
        subject = "";
        toStr = "";
        html = "";
      } else if (mode === "reply") {
        const fromObj = msg?.from_email || ov?.from_email;
        if (fromObj) toStr = formatAddress(fromObj);

        subject = originalSubj.toLowerCase().startsWith("re:") ? originalSubj : originalSubj ? `Re: ${originalSubj}` : "";
        const rawQuote = buildQuotedOriginalBodyHtml(ov, msg);
        html = "\n" + sanitizeForComposer(rawQuote);
      } else if (mode === "reply_all") {
        const fromObj = msg?.from_email || ov?.from_email;
        const toList = msg?.to || ov?.to || [];
        const ccList = msg?.cc || [];

        const allRecipients = [
          ...(fromObj ? [fromObj] : []),
          ...toList,
          ...ccList,
        ];

        toStr = formatAddressList(allRecipients);

        subject = originalSubj.toLowerCase().startsWith("re:") ? originalSubj : originalSubj ? `Re: ${originalSubj}` : "";
        const rawQuote = buildQuotedOriginalBodyHtml(ov, msg);
        html = "\n" + sanitizeForComposer(rawQuote);
      } else if (mode === "forward") {
        subject = originalSubj.toLowerCase().startsWith("fwd:") ? originalSubj : originalSubj ? `Fwd: ${originalSubj}` : "";
        const rawFwd = buildForwardedOriginalBodyHtml(ov, msg);
        html = "\n" + sanitizeForComposer(rawFwd);
      }

      const to = splitRawList(toStr);

      setState((s) => ({
        ...s,
        open: true,
        minimized: false,
        mode,
        error: "",
        attachments: [],

        extra: { cc: false, bcc: false, replyto: false, priority: false },

        to,
        cc: [],
        bcc: [],
        subject,
        replyToRaw: "",
        priority: "medium",
        fromAccount: defaultFrom,
        html,
      }));
    },
    [args.selectedOverview, args.selectedMessage, args.getSelectedRef, accounts]
  );

  const minimizeToggle = useCallback(() => {
    setState((s) => ({ ...s, minimized: !s.minimized }));
  }, []);

  const send = useCallback(async () => {
    setError("");

    const mode = state.mode;
    const fromAccount = state.fromAccount;
    const subject = state.subject;

    const toList = state.to;
    const ccList = state.cc;
    const bccList = state.bcc;

    const replyToList = splitRawList(state.replyToRaw);
    const priority = state.priority; // always set
    const attachments = state.attachments;

    const html = (state.html || "").trim();
    const text = stripHtmlToText(html);

    if (!fromAccount) {
      setError("Please select a From account.");
      return;
    }

    if ((mode === "compose" || mode === "forward") && !toList.length) {
      setError("Please specify at least one recipient.");
      return;
    }

    let ref: EmailRef | null = null;
    if (mode !== "compose") {
      ref = args.getSelectedRef();
      if (!ref) {
        setError("No email selected to reply or forward.");
        return;
      }
    }

    try {
      if (mode === "compose") {
        await EmailApi.sendEmail({
          account: fromAccount,
          subject,
          to: toList,
          fromAddr: fromAccount,
          cc: ccList,
          bcc: bccList,
          text,
          html: html || undefined,
          replyTo: replyToList,
          priority,
          attachments,
        });
      } else if (mode === "reply") {
        await EmailApi.replyEmail({
          ...ref!,
          text: text,
          html: html || undefined,
          fromAddr: fromAccount,
          quoteOriginal: false,
          to: toList,
          cc: ccList,
          bcc: bccList,
          subject,
          replyTo: replyToList,
          priority,
          attachments,
        });
      } else if (mode === "reply_all") {
        await EmailApi.replyAllEmail({
          ...ref!,
          text: text,
          html: html || undefined,
          fromAddr: fromAccount,
          quoteOriginal: false,
          to: toList,
          cc: ccList,
          bcc: bccList,
          subject,
          replyTo: replyToList,
          priority,
          attachments,
        });
      } else if (mode === "forward") {
        await EmailApi.forwardEmail({
          ...ref!,
          to: toList,
          text: text,
          html: html || undefined,
          fromAddr: fromAccount,
          includeOriginal: false,
          includeAttachments: true,
          cc: ccList,
          bcc: bccList,
          subject,
          replyTo: replyToList,
          priority,
          attachments,
        });
      } else {
        setError("Unknown composer mode.");
        return;
      }

      reset();
      close();
    } catch (e) {
      console.error("Error sending:", e);
      setError("Failed to send message. Please try again.");
    }
  }, [state, args.getSelectedRef, reset, close, setError]);

  const saveDraft = useCallback(async (): Promise<boolean> => {
    setError("");

    const fromAccount = state.fromAccount;
    if (!fromAccount) {
      setError("Please select a From account before saving a draft.");
      return false;
    }

    const toDraft = splitRawList(getAddressDraft("composer-to"));
    const ccDraft = splitRawList(getAddressDraft("composer-cc"));
    const bccDraft = splitRawList(getAddressDraft("composer-bcc"));

    const subject = state.subject;

    const toList = mergeUniqueCaseInsensitive(state.to, toDraft);
    
    const ccList = mergeUniqueCaseInsensitive(state.cc, ccDraft);
    const bccList = mergeUniqueCaseInsensitive(state.bcc, bccDraft);

    const replyToList = splitRawList(state.replyToRaw);
    const priority = state.priority;

    const html = (state.html || "").trim();
    const text = stripHtmlToText(html);

    const attachments = state.attachments;

    const draftsMailbox =
      guessDraftsMailbox(args.mailboxData[fromAccount]) ??
      "Drafts";

    try {
      await EmailApi.saveDraft({
        account: fromAccount,
        subject,
        to: toList,
        fromAddr: fromAccount,
        cc: ccList,
        bcc: bccList,
        text,
        html: html || undefined,
        replyTo: replyToList,
        priority,
        draftsMailbox,
        attachments,
      });
      return true;
    } catch (e) {
      console.error("Error saving draft:", e);
      setError("Failed to save draft. Please try again.");
      return false;
    }
  }, [state, args.mailboxData, setError]);

  return {
    state,
    accounts,

    open,
    requestClose,
    close,
    reset,

    minimizeToggle,
    toggleExtraField,

    setFromAccount,
    setPriority,
    setReplyToRaw,
    setSubject,
    setHtml,

    setTo,
    setCc,
    setBcc,

    addAttachments,
    removeAttachmentAt,

    send,
    saveDraft,
  };
}
