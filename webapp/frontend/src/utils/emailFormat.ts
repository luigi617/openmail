// src/utils/emailFormat.ts
import type { EmailAddress, EmailOverview, MailboxData } from "../types/email";


export const COLOR_PALETTE = [
  "#f97316",
  "#22c55e",
  "#0ea5e9",
  "#a855f7",
  "#ec4899",
  "#eab308",
  "#10b981",
  "#f97373",
] as const;

export function formatDate(value: unknown, verbose?: boolean): string {
  if (!value) return "";
  const date = new Date(value as any);
  if (Number.isNaN(date.getTime())) return String(value);

  if (verbose) {
    return date.toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  return date.toLocaleString(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// export function formatDate(value: unknown, verbose?: boolean): string {
//   if (!value) return "";

//   const date = new Date(value as any);
//   if (Number.isNaN(date.getTime())) return String(value);

//   const now = new Date();

//   // Normalize to midnight for date-only comparisons
//   const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
//   const yesterday = new Date(today);
//   yesterday.setDate(today.getDate() - 1);

//   const targetDay = new Date(
//     date.getFullYear(),
//     date.getMonth(),
//     date.getDate()
//   );

//   if (targetDay.getTime() === today.getTime()) {
//     // Today → time only (24h)
//     return date.toLocaleTimeString(undefined, {
//       hour: "2-digit",
//       minute: "2-digit",
//       hour12: false,
//     });
//   }

//   if (targetDay.getTime() === yesterday.getTime()) {
//     // Yesterday
//     return "Yesterday";
//   }

//   // Older → date only
//   return date.toLocaleDateString(undefined, {
//     year: verbose ? "numeric" : undefined,
//     month: "short",
//     day: "2-digit",
//   });
// }

export function escapeHtml(str: unknown): string {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function formatAddress(addr?: EmailAddress | null): string {
  if (!addr) return "";
  if (addr.name && addr.email) return `${addr.name} <${addr.email}>`;
  if (addr.name) return addr.name;
  return addr.email || "";
}

export function formatAddressList(list?: EmailAddress[] | null): string {
  if (!Array.isArray(list)) return "";
  return list.map(formatAddress).filter(Boolean).join(", ");
}

export function getEmailId(email?: EmailOverview | null): string {
  if (!email) return "";
  const ref = email.ref || {};
  if (ref.uid != null) {
    const account = ref.account || "";
    const mailbox = ref.mailbox || "";
    return `${account}:${mailbox}:${String(ref.uid)}`;
  }
  return email.ref.uid.toString();
}

export function getAccountKey(email?: EmailOverview | null): string {
  if (!email) return "unknown";
  return email.ref.account || "unknown";
}

export function findAccountForEmail(email: EmailOverview | null | undefined, mailboxData: MailboxData): string {
  if (!email) return "unknown";

  const ref = email.ref || {};
  if (ref.account) return ref.account;

  const mailboxAccounts = Object.keys(mailboxData || {});
  if (!mailboxAccounts.length) return getAccountKey(email);

  const toList = Array.isArray(email.to) ? email.to : [];
  const toEmails = new Set(
    toList
      .map((a) => (a?.email ? a.email.toLowerCase() : ""))
      .filter(Boolean)
  );

  for (const account of mailboxAccounts) {
    if (toEmails.has(String(account).toLowerCase())) return account;
  }

  if (email.to) {
    const rawTo = String(email.to).toLowerCase();
    for (const account of mailboxAccounts) {
      if (rawTo.includes(String(account).toLowerCase())) return account;
    }
  }

  return getAccountKey(email);
}

export function buildColorMap(emails: EmailOverview[], mailboxData: MailboxData): Record<string, string> {
  const map: Record<string, string> = {};
  let colorIndex = 0;

  for (const account of Object.keys(mailboxData || {})) {
    if (!map[account]) {
      map[account] = COLOR_PALETTE[colorIndex % COLOR_PALETTE.length];
      colorIndex++;
    }
  }

  for (const email of emails || []) {
    const key = findAccountForEmail(email, mailboxData);
    if (!map[key]) {
      map[key] = COLOR_PALETTE[colorIndex % COLOR_PALETTE.length];
      colorIndex++;
    }
  }

  return map;
}

export function getColorForEmail(
  email: EmailOverview,
  mailboxData: MailboxData,
  colorMap: Record<string, string>
): string {
  const key = findAccountForEmail(email, mailboxData);
  return colorMap?.[key] || "#9ca3af";
}

export function getMailboxDisplayName(raw: unknown): string {
  if (!raw) return "";

  let name = String(raw).trim();

  const gmailPrefix = "[Gmail]/";
  if (name.startsWith(gmailPrefix)) name = name.slice(gmailPrefix.length).trim();

  name = name.replace(/^INBOX[/.]/i, "").trim();

  const slashIdx = name.lastIndexOf("/");
  const dotIdx = name.lastIndexOf(".");
  const sepIdx = Math.max(slashIdx, dotIdx);
  if (sepIdx !== -1) name = name.slice(sepIdx + 1).trim();

  const lower = name.toLowerCase();

  const specialMap: Record<string, string> = {
    inbox: "Inbox",
    sent: "Sent",
    "sent mail": "Sent",
    "sent items": "Sent",
    "sent messages": "Sent",
    draft: "Drafts",
    drafts: "Drafts",
    trash: "Trash",
    bin: "Trash",
    "deleted items": "Trash",
    "deleted messages": "Trash",
    spam: "Spam",
    junk: "Spam",
    "junk e-mail": "Spam",
    "bulk mail": "Spam",
    archive: "Archive",
    "all mail": "All mail",
    important: "Important",
    starred: "Starred",
  };

  if (specialMap[lower]) return specialMap[lower];
  return name.charAt(0).toUpperCase() + name.slice(1);
}
