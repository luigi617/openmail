// src/types/composer.ts

import type { Priority } from "./shared";

export type ComposerMode = "compose" | "reply" | "reply_all" | "forward";

export type ComposerExtraFieldKey = "cc" | "bcc" | "replyto" | "priority";

export type ComposerState = {
  open: boolean;
  minimized: boolean;
  mode: ComposerMode;

  extra: Record<ComposerExtraFieldKey, boolean>;

  // chips
  to: string[];
  cc: string[];
  bcc: string[];

  subject: string;

  // keep raw string for UI input, parse later if needed
  replyToRaw: string;

  priority: Priority;

  fromAccount: string;
  text: string;
  html: string;
  attachments: File[];

  error: string;
};
