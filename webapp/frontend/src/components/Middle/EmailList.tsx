import { useState } from "react";
import type { EmailOverview } from "../../types/email";
import { formatDate } from "../../utils/emailFormat";

export type EmailListProps = {
  emails: EmailOverview[];
  selectedEmailId: string | null;
  getColorForEmail: (e: EmailOverview) => string;
  getEmailId: (e: EmailOverview) => string;
  onSelectEmail: (email: EmailOverview) => void;

  // NEW:
  listRef: React.RefObject<HTMLDivElement | null>;
  sentinelRef: React.RefObject<HTMLDivElement | null>;
  showLoadingMore: boolean;
  showEnd: boolean;
  emptyList: boolean;
};

function stableFallbackKey(email: EmailOverview, index: number) {
  const a = email.ref.account ?? "";
  const m = email.ref.mailbox ?? "";
  const u = email.ref.uid ?? "";
  const raw = `${a}:${m}:${String(u)}`;
  return raw !== "::" ? raw : `row-${index}`;
}

function isSeenFromFlags(flags: unknown): boolean {
  if (!Array.isArray(flags)) return false;
  return flags.some((f) => {
    const s = String(f).toLowerCase();
    return s.includes("seen") || s === "read" || s.includes("\\seen");
  });
}

export default function EmailList(props: EmailListProps) {
  const [uiSeenKeys, setUiSeenKeys] = useState<Set<string>>(() => new Set());

  return (
    <div
      id="email-list"
      className="email-list"
      ref={(el) => {
        props.listRef.current = el;
      }}
    >
      {props.emails.map((email, index) => {
        const emailId = props.getEmailId(email);
        const key = emailId || stableFallbackKey(email, index);
        const isSelected = !!emailId && emailId === props.selectedEmailId;

        const isSeenFromServer = isSeenFromFlags((email as any).flags);
        const isSeen = isSeenFromServer || uiSeenKeys.has(key);
        const isUnread = !isSeen;

        const color = props.getColorForEmail(email);
        const fromAddr =
          email.from_email?.name || email.from_email?.email || "(unknown sender)";
        const dateStr = formatDate(email.received_at);
        const subj = email.subject || "(no subject)";

        return (
          <div
            key={key}
            className={`email-card ${isSelected ? "selected" : ""} ${
              isUnread ? "unread" : "read"
            }`}
            onClick={() => {
              setUiSeenKeys((prev) => {
                if (prev.has(key)) return prev;
                const next = new Set(prev);
                next.add(key);
                return next;
              });

              props.onSelectEmail(email);
            }}
            role="button"
            tabIndex={0}
            aria-selected={isSelected}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                setUiSeenKeys((prev) => {
                  if (prev.has(key)) return prev;
                  const next = new Set(prev);
                  next.add(key);
                  return next;
                });
                props.onSelectEmail(email);
              }
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

            {isUnread ? <div className="email-unread-dot" aria-hidden="true" /> : null}
          </div>
        );
      })}

      <div className={`empty-state ${props.emptyList ? "" : "hidden"}`}>
        No emails match the current filters.
      </div>

      <div ref={(el) => {props.sentinelRef.current = el}} style={{ height: 1 }} />

      {props.showLoadingMore ? <div className="list-loading">Loading more…</div> : null}
      {props.showEnd ? <div className="list-end">End of results</div> : null}
    </div>
  );
}
