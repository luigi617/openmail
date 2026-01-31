// src/types/shared.ts

export type EmailRef = {
  account: string;
  uid: number;
  mailbox: string;
};

export type Priority = "high" | "medium" | "low";

export type ApiErrorPayload = {
  message?: string;
  detail?: string;
};
