import React, { useMemo } from "react";

function htmlToText(html: string) {
  // Safer + preserves spacing better than regex
  const div = document.createElement("div");
  div.innerHTML = html;

  // Remove script/style
  div.querySelectorAll("script,style,noscript").forEach((n) => n.remove());

  return (div.textContent || "").replace(/\n{3,}/g, "\n\n").trim();
}

export type DetailBodyProps = {
  html?: string | null;
  text?: string | null;
};

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
        <div dangerouslySetInnerHTML={{ __html: html }} />
      </div>
    );
  }

  const safeText = derivedText.trim().length ? derivedText : "";
  return <pre className="detail-body text">{safeText}</pre>;
}
