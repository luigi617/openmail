// src/components/Layout/DetailColumn.tsx
import React, { useMemo, useState } from "react";
import type { EmailMessage, EmailOverview, MailboxData } from "../../types/email"
import { getMailboxDisplayName } from "../../utils/emailFormat";
import { getDetailHeader } from "../../utils/detailFormat";
import DetailBody from "../Detail/DetailBody";
import DetailToolbar from "../Detail/DetailToolbar";
import DetailAttachments from "../Detail/DetailAttachments";

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

export default function DetailColumn(props: DetailColumnProps) {
  const [moveOpen, setMoveOpen] = useState(false);

  const moveOptions = useMemo(() => {
    const ov = props.selectedOverview;
    if (!ov) return [];
    const account = ov.ref.account;
    if (!account) return [];
    return props.mailboxData[account] ?? [];
  }, [props.selectedOverview, props.mailboxData]);

  const [destinationMailbox, setDestinationMailbox] = useState<string>(() => props.currentMailbox);


  // keep destination in sync when mailbox changes or selection changes
  React.useEffect(() => {
    setDestinationMailbox(props.currentMailbox);
  }, [props.currentMailbox, props.selectedOverview]);

  const header = useMemo(() => {
    if (!props.selectedOverview && !props.selectedMessage) return null;
    return getDetailHeader(props.selectedOverview, props.selectedMessage);
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
          {/* toolbar */}
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

          {/* header */}
          {header && (
            <>
              <div className="detail-header">
                <span
                  className="detail-badge"
                  style={{ background: props.getColorForEmail(props.selectedOverview) }}
                />
                <div className="detail-meta">
                  <div id="detail-subject" className="detail-subject">
                    {header.subject}
                  </div>
                  <div id="detail-from" className="detail-line">
                    {header.fromLine}
                  </div>
                  <div id="detail-to" className="detail-line">
                    {header.toLine}
                  </div>
                  <div id="detail-datetime" className="detail-line small">
                    {header.dateLine}
                  </div>
                </div>
              </div>
              <hr />

              <DetailBody html={header.html} text={header.text} />
              {/* ✅ Attachments like DetailBody: separate component */}
              {props.selectedMessage && props.selectedMessage.attachments.length > 0 && (
                <>
                  <hr />
                  <DetailAttachments 
                    attachments={props.selectedMessage?.attachments} 
                    account={props.selectedMessage.ref.account}
                    email_id={props.selectedMessage.ref.uid}
                    mailbox={props.selectedMessage.ref.mailbox}
                  />
                </>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}
