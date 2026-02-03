// src/utils/messageBuilders.ts
import { escapeHtml, formatAddressList } from "./emailFormat";
import type { EmailOverview, EmailMessage, EmailAddress } from "../types/email";

function senderLabel(fromObj?: EmailAddress) {
  if (!fromObj) return "unknown sender";
  if (fromObj.name && fromObj.email) return `${fromObj.name} <${fromObj.email}>`;
  return fromObj.name || fromObj.email || "unknown sender";
}

function preferOriginalHtml(msg?: EmailMessage | null, ov?: EmailOverview | null) {
  if (msg?.html) return msg.html;
  if (msg?.text) return `<pre>${escapeHtml(msg.text)}</pre>`;
  return "";
}

export function buildQuotedOriginalBodyHtml(overview: EmailOverview | null, msg: EmailMessage | null) {
  if (!overview && !msg) return "";

  const fromObj = msg?.from_email || overview?.from_email;
  const who = senderLabel(fromObj);

  const dateVal = msg?.date || overview?.date;
  let headerLine = "";

  if (dateVal) {
    const d = new Date(dateVal as any);
    if (!Number.isNaN(d.getTime())) {
      const dateStr = d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
      const timeStr = d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
      headerLine = `On ${dateStr}, at ${timeStr}, ${who} wrote:`;
    } else {
      headerLine = `On ${String(dateVal)}, ${who} wrote:`;
    }
  } else {
    headerLine = `${who} wrote:`;
  }

  const originalHtml = preferOriginalHtml(msg, overview);
  const safeHeader = escapeHtml(headerLine);

  const html = !originalHtml
    ? `<p>${safeHeader}</p>`
    : `<div class="quoted-wrapper"><div class="quoted-header">${safeHeader}</div><blockquote class="quoted-original">${originalHtml}</blockquote></div>`;

  return html.replace(/>\s+</g, "><").trim();
}

export function buildForwardedOriginalBodyHtml(overview: EmailOverview | null, msg: EmailMessage | null) {
  if (!overview && !msg) return "";

  const fromObj = msg?.from_email || overview?.from_email;
  const who = senderLabel(fromObj);

  const dateVal = msg?.date || overview?.date;
  let dateLine = "";
  if (dateVal) {
    const d = new Date(dateVal as any);
    if (!Number.isNaN(d.getTime())) {
      dateLine = d.toLocaleString(undefined, {
        weekday: "short",
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
        hour12: true,
      });
    } else {
      dateLine = String(dateVal);
    }
  }

  const originalSubj = msg?.subject || overview?.subject || "(no subject)";
  const toList = msg?.to || overview?.to || [];
  const toAddr = formatAddressList(toList);

  const originalHtml = preferOriginalHtml(msg, overview);

  const headerLines = [
    "---------- Forwarded message ---------",
    `From: ${who}`,
    dateLine ? `Date: ${dateLine}` : null,
    `Subject: ${originalSubj}`,
    toAddr ? `To: ${toAddr}` : null,
  ].filter(Boolean) as string[];

  const headerHtml = headerLines.map((line) => escapeHtml(line)).join("<br>");

  const html =
    `<div class="forwarded-wrapper">` +
    `<div class="forwarded-header">${headerHtml}</div>` +
    (originalHtml ? `<br>${originalHtml}` : "") +
    `</div>`;

  return html.replace(/>\s+</g, "><").trim();
}
