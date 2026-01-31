// src/types/api.ts
import type { Priority } from "./shared";

export type OverviewParams = {
  mailbox?: string;
  limit?: number;
  cursor?: string;
  accounts?: string[];
};

export type OverviewResponse<TEmail> = {
  data: TEmail[];
  meta?: {
    next_cursor?: string | null;
    prev_cursor?: string | null;
    result_count?: number | null;
    total_count?: number | null;
  };
};

export type ComposeParamsBase = {
  account: string;
  subject?: string;
  to?: string[];
  cc?: string[];
  bcc?: string[];
  fromAddr?: string;
  replyTo?: string[];
  priority?: Priority;
  text?: string;
  html?: string;
  attachments?: File[];
};

export type SendEmailParams = ComposeParamsBase;

export type SaveDraftParams = ComposeParamsBase & {
  draftsMailbox?: string;
};

export type ReplyParams = ComposeParamsBase & {
  uid: number;
  mailbox: string;
  quoteOriginal?: boolean;
};

export type ForwardParams = ComposeParamsBase & {
  uid: number;
  mailbox: string;
  includeOriginal?: boolean;
  includeAttachments?: boolean;
};
