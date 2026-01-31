import React from "react";
import type { EmailOverview } from "../../types/email";
import { formatDate } from "../../utils/emailFormat";

export type EmailListProps = {
  emails: EmailOverview[];
  selectedEmailId: string | null;
  getColorForEmail: (e: EmailOverview) => string;
  getEmailId: (e: EmailOverview) => string;
  onSelectEmail: (email: EmailOverview) => void;
};

function stableFallbackKey(email: EmailOverview, index: number) {
  // Prefer a deterministic key even if getEmailId is empty
  const a = email.ref.account ?? "";
  const m = email.ref.mailbox ?? "";
  const u = email.ref.uid ?? "";
  const raw = `${a}:${m}:${String(u)}`;
  return raw !== "::" ? raw : `row-${index}`;
}

export default function EmailList(props: EmailListProps) {
  return (
    <div id="email-list" className="email-list">
      {props.emails.map((email, index) => {
        const emailId = props.getEmailId(email);
        const key = emailId || stableFallbackKey(email, index);
        const isSelected = !!emailId && emailId === props.selectedEmailId;

        const color = props.getColorForEmail(email);
        const fromAddr = email.from_email?.name || email.from_email?.email || "(unknown sender)";
        const dateStr = formatDate(email.date);
        const subj = email.subject || "(no subject)";

        return (
          <div
            key={key}
            className={`email-card ${isSelected ? "selected" : ""}`}
            onClick={() => props.onSelectEmail(email)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") props.onSelectEmail(email);
            }}
          >
            <div className="email-color-strip" style={{ background: color }} />
            <div className="email-main">
              <div className="email-row-top">
                <div className="email-from">{fromAddr}</div>
                <div className="email-date">{dateStr}</div>
              </div>
              <div className="email-subject">{subj}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
