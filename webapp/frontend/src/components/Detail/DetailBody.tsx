import { useEffect, useMemo, useRef } from 'react';
import DOMPurify from 'dompurify';
import type { Attachment } from '../../types/email';
import DetailAttachments from './DetailAttachments';

/**
 * Basic HTML -> text fallback
 */
function htmlToText(html: string) {
  const div = document.createElement('div');
  div.innerHTML = html;
  div.querySelectorAll('script,style,noscript').forEach((n) => n.remove());
  return (div.textContent || '').replace(/\n{3,}/g, '\n\n').trim();
}

export type DetailBodyProps = {
  account: string;
  mailbox: string;
  email_id: number;
  html?: string | null;
  text?: string | null;
  attachments?: Attachment[];
};

/**
 * Sanitize email HTML for rendering inside Shadow DOM.
 *
 * Notes:
 * - We forbid scripts/iframes/embeds/forms/event handlers.
 * - We also forbid <style> by default for stability (recommended).
 *   If you want higher fidelity, remove "style" from FORBID_TAGS.
 */
function sanitizeEmailHtml(html: string) {
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },

    FORBID_TAGS: [
      'script',
      'style', // remove this if you want to allow email-provided <style>
      'noscript',
      'iframe',
      'object',
      'embed',
      'base',
      'meta',
      'link',
      'form',
      'input',
      'button',
      'textarea',
      'select',
    ],

    FORBID_ATTR: [
      // common event handlers
      'onload',
      'onclick',
      'onerror',
      'onmouseover',
      'onfocus',
      'onsubmit',
      'onmouseenter',
      'onmouseleave',
      'onkeydown',
      'onkeyup',
      'onkeypress',
      'oninput',
      'onchange',
    ],

    // Optional hardening knobs:
    // ALLOW_UNKNOWN_PROTOCOLS: false,
  });
}

/**
 * Shadow DOM email renderer (no iframe).
 * - isolates styles to avoid email CSS leaking into your app
 * - natural height (no iframe resizing issues)
 */
function EmailShadowBody({ html }: { html: string }) {
  const hostRef = useRef<HTMLDivElement | null>(null);

  const safeHtml = useMemo(() => sanitizeEmailHtml(html), [html]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    const shadow = host.shadowRoot ?? host.attachShadow({ mode: 'open' });

    // Clear existing content
    while (shadow.firstChild) shadow.removeChild(shadow.firstChild);

    // Base styles inside ShadowRoot for consistent rendering
    const style = document.createElement('style');
    style.textContent = `
      :host { display: block; }

      .email-root {
        /* Your forced light theme */
        color-scheme: light;
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        font-size: 14px;
        line-height: 1.45;
        color: #111827;
        background: transparent;
        overflow-wrap: anywhere;
        word-break: break-word;
        padding: 6px;
      }

      /* Clamp common troublesome elements */
      img {
        max-width: 100%;
        height: auto;
      }

      table {
        max-width: 100%;
        width: auto !important;
        border-collapse: collapse;
      }

      pre, code {
        white-space: pre-wrap;
        word-break: break-word;
      }

      blockquote {
        margin: 0.5rem 0;
        padding-left: 0.75rem;
        border-left: 3px solid rgba(127,127,127,0.35);
      }

      a { color: #0a84ff; }

      hr {
        border: none;
        border-top: 1px solid rgba(127,127,127,0.35);
        margin: 12px 0;
      }

      /* Prevent overly wide fixed-width stuff */
      * {
        max-width: 100%!important;
        box-sizing: border-box;
      }
    `;

    const root = document.createElement('div');
    root.className = 'email-root';
    root.innerHTML = safeHtml;

    shadow.appendChild(style);
    shadow.appendChild(root);

    // Harden links (in shadow root)
    shadow.querySelectorAll('a[href]').forEach((a) => {
      a.setAttribute('target', '_blank');
      a.setAttribute('rel', 'noopener noreferrer');
    });

    // Optional: prevent mixed-content images from breaking layout
    // and ensure images trigger layout changes naturally (no need for resize hacks).
    // If you want to add placeholders, you can handle it here.
  }, [safeHtml]);

  return <div ref={hostRef} />;
}

export default function DetailBody(props: DetailBodyProps) {
  const html = props.html ?? '';
  const text = props.text ?? '';
  const hasHtml = html.trim().length > 0;

  const derivedText = useMemo(() => {
    if (text.trim().length) return text;
    if (hasHtml) return htmlToText(html);
    return '';
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
          <EmailShadowBody html={html} />
        </div>
        {AttachmentsInline}
      </div>
    );
  }

  const safeText = derivedText.trim().length ? derivedText : '';
  return (
    <div className="detail-body-block">
      <pre className="detail-body text">{safeText}</pre>
      {AttachmentsInline}
    </div>
  );
}
