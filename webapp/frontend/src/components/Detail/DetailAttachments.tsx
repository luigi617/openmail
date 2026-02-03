import { useMemo } from 'react';
import type { Attachment } from '../../types/email';
import DownloadIcon from '../../assets/svg/download.svg?react';

export type DetailAttachmentsProps = {
  attachments?: (Attachment | null | undefined)[] | null;
  // Needed to build the EmailRef link
  account: string;
  mailbox: string;
  email_id: number;
};

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  let v = bytes;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  const decimals = i === 0 ? 0 : v < 10 ? 1 : 0;
  return `${v.toFixed(decimals)} ${units[i]}`;
}

function safeFilename(name: string) {
  const cleaned = name.replace(/[<>:"/\\|?*]/g, '_').trim();

  const withoutControls = Array.from(cleaned, (ch) => (ch.charCodeAt(0) < 32 ? '_' : ch)).join('');

  return withoutControls || 'attachment';
}

function buildDownloadUrl(params: {
  account: string;
  mailbox: string;
  email_id: number;
  part: string;
  filename: string;
  content_type: string;
}): string {
  const { account, mailbox, email_id, part, filename, content_type } = params;

  const base =
    `/api/accounts/${encodeURIComponent(account)}` +
    `/mailboxes/${encodeURIComponent(mailbox)}` +
    `/emails/${encodeURIComponent(String(email_id))}` +
    `/attachment`;

  const qs = new URLSearchParams();
  qs.set('part', part);
  qs.set('filename', filename);
  qs.set('content_type', content_type);

  // Optional; backend does not require these
  if (filename) qs.set('filename', safeFilename(filename));
  if (content_type) qs.set('content_type', content_type);

  return `${base}?${qs.toString()}`;
}

/**
 * Trigger download via a direct link to the backend.
 * This avoids loading bytes into JS memory.
 */
function triggerDownload(url: string) {
  const a = document.createElement('a');
  a.href = url;
  a.rel = 'noopener';
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

export default function DetailAttachments(props: DetailAttachmentsProps) {
  const attachments = useMemo(() => {
    const a = props.attachments ?? [];
    return Array.isArray(a) ? (a.filter((att) => att && !att.is_inline) as Attachment[]) : [];
  }, [props.attachments]);

  if (attachments.length === 0) return null;

  return (
    <div className="detail-attachments" id="detail-attachments">
      <div className="detail-attachments-title detail-line">Attachments</div>

      <div className="detail-attachments-strip" role="list" aria-label="Attachments">
        {attachments.map((att, idx) => {
          const fullName = att.filename || `Attachment ${idx + 1}`;
          const size = typeof att.size === 'number' ? formatBytes(att.size) : '';

          // IMPORTANT: use IMAP part from meta
          const part = att.part;

          const canDownload = Boolean(part && part.trim().length > 0);

          const url = canDownload
            ? buildDownloadUrl({
                account: props.account,
                mailbox: props.mailbox,
                email_id: props.email_id,
                part: part!.trim(),
                filename: att.filename,
                content_type: att.content_type,
              })
            : '';

          const onActivate = () => {
            if (!canDownload) return;
            triggerDownload(url);
          };

          return (
            <div
              key={att.idx ?? `${fullName}-${idx}`}
              className={`attachment-card ${canDownload ? '' : 'is-disabled'}`}
              role="listitem"
              title={fullName}
              tabIndex={canDownload ? 0 : -1}
              aria-disabled={!canDownload}
              onClick={onActivate}
              onKeyDown={(e) => {
                if (!canDownload) return;
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  onActivate();
                }
              }}
            >
              <div className="attachment-card-main">
                <div className="attachment-card-name" title={fullName}>
                  {fullName}
                </div>
                <div className="attachment-card-size detail-line small">{size || ' '}</div>
              </div>

              {/* Use a normal link so right-click "Save link as" works */}
              {canDownload ? (
                <a
                  className="icon-btn attachment-card-action"
                  href={url}
                  onClick={(e) => e.stopPropagation()}
                  aria-label={`Download ${fullName}`}
                  title={`Download ${fullName}`}
                >
                  <DownloadIcon className="icon" aria-hidden />
                </a>
              ) : (
                <button
                  type="button"
                  className="icon-btn attachment-card-action"
                  disabled
                  aria-label={`Download ${fullName}`}
                  title="No attachment part available"
                >
                  <DownloadIcon className="icon" aria-hidden />
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
