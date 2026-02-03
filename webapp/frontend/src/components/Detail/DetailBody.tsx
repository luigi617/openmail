import React, { useEffect, useMemo, useRef } from "react";
import DOMPurify from "dompurify";

function htmlToText(html: string) {
  const div = document.createElement("div");
  div.innerHTML = html;
  div.querySelectorAll("script,style,noscript").forEach((n) => n.remove());
  return (div.textContent || "").replace(/\n{3,}/g, "\n\n").trim();
}

export type DetailBodyProps = {
  html?: string | null;
  text?: string | null;
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
  // No scripts. Keep styling inside iframe only.
  // "base target=_blank" ensures links don't navigate inside the iframe.
  // (Also add rel protections in-case some clients rely on it.)
  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="referrer" content="no-referrer" />
  <base target="_blank" />
  <style>
    html, body { margin: 0; padding: 0; }
    body {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 14px;
      line-height: 1.35;
      color: #111827;
      background: transparent;
      overflow-wrap: anywhere;
    }
    img { max-width: 100%; height: auto; }
    table { max-width: 100%; }
    pre { white-space: pre-wrap; }
    a { color: inherit; }
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

    // Resize iframe to content height.
    // This requires SAME-ORIGIN access; srcDoc gives that.
    const onLoad = () => {
      try {
        const doc = iframe.contentDocument;
        if (!doc) return;

        // Add rel to all links for safety (base already sets target=_blank).
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

        // Observe changes (images loading, fonts, etc.)
        const ro = new ResizeObserver(() => resize());
        ro.observe(doc.documentElement);

        // Also listen for late-loading images
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
      // Strictest: no scripts. allow-popups lets target=_blank work.
      // allow-top-navigation is NOT granted, so links can't take over the tab.
      sandbox="allow-popups allow-popups-to-escape-sandbox"
      srcDoc={srcDoc}
      style={{
        width: "100%",
        border: "0",
        display: "block",
        background: "transparent",
      }}
      // Optional: keep it out of tab order
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

  if (hasHtml) {
    return (
      <div className="detail-body html">
        <EmailIFrame html={html} />
      </div>
    );
  }

  const safeText = derivedText.trim().length ? derivedText : "";
  return <pre className="detail-body text">{safeText}</pre>;
}
