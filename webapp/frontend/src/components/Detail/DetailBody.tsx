import { useEffect, useMemo, useRef } from "react";
import DOMPurify from "dompurify";
import type { Attachment } from "../../types/email";
import DetailAttachments from "./DetailAttachments";

function htmlToText(html: string) {
  const div = document.createElement("div");
  div.innerHTML = html;
  div.querySelectorAll("script,style,noscript").forEach((n) => n.remove());
  return (div.textContent || "").replace(/\n{3,}/g, "\n\n").trim();
}

export type DetailBodyProps = {
  account: string;
  mailbox: string;
  email_id: number;
  html?: string | null;
  text?: string | null;
  attachments?: Attachment[];
};

function sanitizeEmailHtml(html: string) {
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
    FORBID_TAGS: [
      "script",
      "style",
      "noscript",
      "iframe",
      "object",
      "embed",
      "base",
      "meta",
      "link",
      "link",
      "form",
      "input",
      "button",
      "textarea",
      "select",
    ],
    FORBID_ATTR: [
      "onload",
      "onclick",
      "onerror",
      "onmouseover",
      "onfocus",
      "onsubmit",
    ],
  });
}

function buildSrcDoc(safeBodyHtml: string) {
  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="referrer" content="no-referrer" />
  <base target="_blank" />

  <!-- Force light theme only -->
  <meta name="color-scheme" content="light" />
  <meta name="supported-color-schemes" content="light" />

  <style>
    :root {
      color-scheme: light;

      --email-text: #111827;
      --email-muted: #6b7280;
      --email-link: #0a84ff;

      /* background stays transparent so your .detail-body shell shows */
      --email-bg: transparent;
    }

    html, body { margin: 0; padding: 5px; overflow: hidden; }
    body {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 14px;
      line-height: 1.35;
      color: var(--email-text);
      background: var(--email-bg);
      overflow-wrap: anywhere;
      border-radius: 8px;
    }

    img { max-width: 100%; height: auto; }
    table { max-width: 100%; }
    pre { white-space: pre-wrap; }

    a { color: var(--email-link); }
    hr { border: none; border-top: 1px solid rgba(127,127,127,0.35); }

    /* Some emails hardcode black text; this nudges toward inheriting */
    #email-root { color: inherit; }
  </style>
</head>
<body>
  <div id="email-root">${safeBodyHtml}</div>
</body>
</html>`;
}

function EmailIFrame({ html }: { html: string }) {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);

  const srcDoc = useMemo(() => {
    const safe = sanitizeEmailHtml(html);
    return buildSrcDoc(safe);
  }, [html]);

  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe) return;

    const onLoad = () => {
      try {
        const doc = iframe.contentDocument;
        if (!doc) return;

        doc.querySelectorAll("a[href]").forEach((a) => {
          a.setAttribute("rel", "noopener noreferrer");
        });

        const resize = () => {
          const body = doc.body;
          const htmlEl = doc.documentElement;
          const height = Math.max(
            body?.scrollHeight ?? 0,
            htmlEl?.scrollHeight ?? 0
          );
          iframe.style.height = `${height}px`;
        };

        resize();

        const ro = new ResizeObserver(() => resize());
        ro.observe(doc.documentElement);

        doc.querySelectorAll("img").forEach((img) => {
          img.addEventListener("load", resize);
          img.addEventListener("error", resize);
        });

        return () => ro.disconnect();
      } catch {
        // If sandbox changes restrict access, height won't auto-adjust.
      }
    };

    iframe.addEventListener("load", onLoad);
    return () => iframe.removeEventListener("load", onLoad);
  }, [srcDoc]);

  return (
    <iframe
      ref={iframeRef}
      title="Email content"
      sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox"
      srcDoc={srcDoc}
      style={{
        width: "100%",
        border: "0",
        display: "block",
        background: "transparent",
        overflow: "hidden",
        height: "0px",
      }}
      tabIndex={-1}
    />
  );
}

export default function DetailBody(props: DetailBodyProps) {
  const html = props.html ?? "";
  const text = props.text ?? "";
  const hasHtml = html.trim().length > 0;
  
  const derivedText = useMemo(() => {
    if (text.trim().length) return text;
    if (hasHtml) return htmlToText(html);
    return "";
  }, [text, hasHtml, html]);

  const attachments = props.attachments ?? [];
  const showAttachments = attachments.length > 0;

  const AttachmentsInline = showAttachments ? (
    <div className="detail-attachments-inline">
      <DetailAttachments
        attachments={attachments}
        account={props.account}
        email_id={props.email_id}
        mailbox={props.mailbox}
      />
    </div>
  ) : null;

  if (hasHtml) {
    return (
      <div className="detail-body-block">
        <div className="detail-body html light-island">
            <EmailIFrame html={html} />  
        </div>
        {AttachmentsInline}
      </div>
    );
  }

  const safeText = derivedText.trim().length ? derivedText : "";
  return (
    <div className="detail-body-block">
      <pre className="detail-body text">{safeText}</pre>
      {AttachmentsInline}
    </div>
  );
}
