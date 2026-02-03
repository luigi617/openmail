// src/components/Layout/DetailColumn.tsx
import { useMemo, useState, useEffect } from "react";
import type { EmailMessage, EmailOverview, MailboxData } from "../../types/email"
import { getMailboxDisplayName } from "../../utils/emailFormat";
import { getDetailHeader } from "../../utils/detailFormat";
import DetailBody from "../Detail/DetailBody";
import DetailToolbar from "../Detail/DetailToolbar";

export type DetailColumnProps = {
  selectedOverview: EmailOverview | null;
  selectedMessage: EmailMessage | null;

  mailboxData: MailboxData;
  currentMailbox: string;

  detailError: string;

  getColorForEmail: (email: EmailOverview) => string;

  onArchive: () => void;
  onDelete: () => void;
  onReply: () => void;
  onReplyAll: () => void;
  onForward: () => void;
  onMove: (destinationMailbox: string) => void;
};

function EmailMessageCard({
  overview,
  message,
  badgeColor,
}: {
  overview: EmailOverview;
  message: EmailMessage | null;
  badgeColor: string;
}) {
  const header = useMemo(() => {
    return getDetailHeader(overview, message);
  }, [overview, message]);

  if (!header) return null;

  return (
    <article className="thread-email-card">
      <div className="detail-header">
        <span className="detail-badge" style={{ background: badgeColor }} />
        <div className="detail-meta">
          <div className="detail-subject">{header.subject}</div>
          <div className="detail-line">{header.fromLine}</div>
          <div className="detail-line">{header.toLine}</div>
          <div className="detail-line small">{header.dateLine}</div>
        </div>
      </div>

      <hr />

      <DetailBody
        account={header.account}
        mailbox={header.mailbox}
        email_id={header.uid as number}
        html={header.html}
        text={header.text}
        attachments={header.attachments}
      />
    </article>
  );
}

export default function DetailColumn(props: DetailColumnProps) {
  const [moveOpen, setMoveOpen] = useState(false);

  const moveOptions = useMemo(() => {
    const ov = props.selectedOverview;
    if (!ov) return [];
    const account = ov.ref.account;
    if (!account) return [];
    return Object.keys(props.mailboxData[account] ?? [])
  }, [props.selectedOverview, props.mailboxData]);

  const [destinationMailbox, setDestinationMailbox] = useState<string>(() => props.currentMailbox);


  // keep destination in sync when mailbox changes or selection changes
  useEffect(() => {
    setDestinationMailbox(props.currentMailbox);
  }, [props.currentMailbox, props.selectedOverview]);

  const threadItems = useMemo(() => {
    if (!props.selectedOverview) return [];
    return [
      {
        overview: props.selectedOverview,
        message: props.selectedMessage,
      },
    ];
  }, [props.selectedOverview, props.selectedMessage]);

  return (
    <section className="card detail-card">
      {!props.selectedOverview ? (
        <div id="detail-placeholder">
          <p className="placeholder-text">
            Select an email from the middle column to see its full content here.
          </p>
        </div>
      ) : (
        <div id="email-detail" className="email-detail">
          {/* toolbar (stays above the scrolling thread) */}
          <DetailToolbar
            onArchive={props.onArchive}
            onDelete={props.onDelete}
            onReply={props.onReply}
            onReplyAll={props.onReplyAll}
            onForward={props.onForward}
            onToggleMove={() => setMoveOpen((v) => !v)}
          />

          <div id="detail-error" className={`inline-error ${props.detailError ? "" : "hidden"}`}>
            {props.detailError}
          </div>

          {/* move panel */}
          {moveOpen && (
            <div className="move-panel">
              <label>
                Move to:
                <select
                  value={destinationMailbox}
                  onChange={(e) => setDestinationMailbox(e.target.value)}
                  id="move-mailbox-select"
                >
                  {moveOptions.map((mb) => (
                    <option key={mb} value={mb}>
                      {getMailboxDisplayName(mb)}
                    </option>
                  ))}
                </select>
              </label>

              <button
                type="button"
                className="secondary small"
                id="move-confirm"
                onClick={() => {
                  if (destinationMailbox) props.onMove(destinationMailbox);
                  setMoveOpen(false);
                }}
              >
                Move
              </button>

              <button
                type="button"
                className="secondary small"
                id="move-cancel"
                onClick={() => setMoveOpen(false)}
              >
                Cancel
              </button>
            </div>
          )}

          {/* THREAD SCROLLER */}
          <div className="detail-thread" role="list">
            {threadItems.map((item) => (
              <div key={`${item.overview.ref.account}:${item.overview.ref.uid}`} role="listitem">
                <EmailMessageCard
                  overview={item.overview}
                  message={item.message}
                  badgeColor={props.getColorForEmail(item.overview)}
                />
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
