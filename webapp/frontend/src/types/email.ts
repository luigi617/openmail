// src/types/email.ts
import type { EmailRef } from "./shared";

export type Mailbox = {
  id: number;
  name: string;
};

// account -> mailbox names (or ids) list
export type MailboxData = Record<string, string[]>;

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
};

export type EmailOverview = {
  ref: EmailRef;
  subject: string;
  from_email: EmailAddress;
  to: EmailAddress[];
  flags: string[];
  headers: Record<string, string>;
  date?: string | null;
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
  date?: string | null;
  message_id?: string | null;
  headers: Record<string, string>;

  accountColor?: string;
};
