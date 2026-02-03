// src/types/email.ts
import type { EmailRef } from "./shared";

export type MailboxStatus = {
  messages?: number;
  unseen?: number;
  [k: string]: number | undefined;
};

// account -> mailbox names (or ids) list
export type MailboxData = Record<string, Record<string, MailboxStatus>>;

export type LegendAccount = {
  id: number;
  label: string;
  color: string;
};

export type EmailAddress = {
  email: string;
  name?: string;
};

export type Attachment = {
  idx: number;
  part: string;
  filename: string;
  content_type: string;
  size: number;
  content_id: string;
  disposition: string;
  is_inline: boolean;
  content_location: string;
};

export type EmailOverview = {
  ref: EmailRef;
  subject: string;
  from_email: EmailAddress;
  to: EmailAddress[];
  flags: string[];
  headers: Record<string, string>;
  received_at?: string | null;
  sent_at?: string | null;
};

export type EmailMessage = {
  ref: EmailRef;
  subject: string;
  from_email: EmailAddress;
  to: EmailAddress[];
  cc: EmailAddress[];
  bcc: EmailAddress[];
  text?: string | null;
  html?: string | null;
  attachments: Attachment[];

  // IMAP metadata
  received_at?: string | null;
  sent_at?: string | null;
  message_id?: string | null;
  headers: Record<string, string>;

  accountColor?: string;
};
