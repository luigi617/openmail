// src/utils/detailFormat.ts
import { formatDate, formatAddressList } from "./emailFormat";
import type { EmailOverview, EmailMessage } from "../types/email";

export function getDetailHeader(overview: EmailOverview | null, msg: EmailMessage | null) {
  const subj = msg?.subject || overview?.subject || "(no subject)";
  const fromObj = msg?.from_email || overview?.from_email;
  const fromAddr = fromObj?.name || fromObj?.email || "(unknown sender)";

  const toList = msg?.to || overview?.to || [];
  const toAddr = formatAddressList(toList);

  const dateVal = msg?.date || overview?.date;
  const dateVerbose = formatDate(dateVal, true);

  return {
    subject: subj,
    fromLine: `From: ${fromAddr}`,
    toLine: toAddr ? `To: ${toAddr}` : "",
    dateLine: `Date: ${dateVerbose}`,
    html: msg?.html || "",
    text: msg?.text || "",
  };
}
