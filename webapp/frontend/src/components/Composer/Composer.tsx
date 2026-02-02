// src/components/Composer/Composer.tsx
import { useRef } from "react";
import { AddressChipsInput } from "./AddressChipsInput";
import ComposerExtraMenu from "./ComposerExtraMenu";
import ComposerEditor from "./ComposerEditor";
import ComposerAttachments from "./ComposerAttachments";
import SendLaterMenu from "./SendLaterMenu";
import { useComposerResize } from "../../hooks/useComposerResize";
import type { ComposerExtraFieldKey } from "../../types/composer";
import type { Priority } from "../../types/shared";

import listIcon from "@/assets/svg/list.svg";
import attachmentIcon from "@/assets/svg/attachment.svg";
import emojiIcon from "@/assets/svg/emoji.svg";
import minimizeIcon from "@/assets/svg/minimize.svg";
import closeIcon from "@/assets/svg/close.svg";

export type ComposerProps = {
  open: boolean;
  onClose: () => void;

  title: string;
  minimized: boolean;

  extraMenuOpen: boolean;
  onToggleExtraMenu: () => void;

  extra: Record<ComposerExtraFieldKey, boolean>;
  onToggleExtraField: (k: ComposerExtraFieldKey) => void;

  to: string[];
  cc: string[];
  bcc: string[];
  onToChange: (v: string[]) => void;
  onCcChange: (v: string[]) => void;
  onBccChange: (v: string[]) => void;

  subject: string;
  onSubjectChange: (v: string) => void;

  replyToRaw: string;
  onReplyToRawChange: (v: string) => void;

  priority: Priority;
  onPriorityChange: (v: Priority) => void;

  fromAccount: string;
  accounts: string[];
  onFromChange: (v: string) => void;

  html: string;
  onHtmlChange: (v: string) => void;

  attachments: File[];
  onAddAttachments: (files: File[]) => void;
  onRemoveAttachmentAt: (idx: number) => void;

  error: string;
  onSend: () => void;

  onMinimizeToggle: () => void;

  sendLaterOpen: boolean;
  onToggleSendLater: () => void;
  onCloseSendLater: () => void;
  onSendLaterPick: (label: string, delayKey: string) => void;

  onCloseExtraMenu: () => void;
};

export default function Composer(props: ComposerProps) {
  const { composerRef, zoneRef } = useComposerResize(props.open);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  return (
    <div
      ref={composerRef}
      className={`composer ${props.open ? "" : "hidden"} ${props.minimized ? "composer--minimized" : ""}`}
    >
      <div ref={zoneRef} className="composer-resize-zone" />

      {/* header */}
      <div className="composer-header">
        <div className="composer-header-left">
          <button
            type="button"
            id="composer-extra-toggle"
            className="composer-icon-btn composer-icon-btn--secondary"
            title="Show fields"
            onClick={(e) => {
              e.stopPropagation();
              props.onToggleExtraMenu();
            }}
          >
            <img src={listIcon} alt="" aria-hidden="true" className="icon-img" />
          </button>

          <ComposerExtraMenu
            open={props.extraMenuOpen}
            onClose={props.onCloseExtraMenu}
            state={props.extra}
            onToggle={props.onToggleExtraField}
          />

          <button
            type="button"
            id="composer-attach"
            className="composer-icon-btn"
            title="Add attachment"
            onClick={() => fileInputRef.current?.click()}
          >
            <img src={attachmentIcon} alt="" aria-hidden="true" className="icon-img" />
          </button>

          <input
            ref={fileInputRef}
            type="file"
            className="composer-file-input"
            multiple
            onChange={(e) => {
              const files = Array.from(e.target.files ?? []);
              if (files.length) props.onAddAttachments(files);
              e.currentTarget.value = "";
            }}
          />

          <button type="button" id="composer-emoji" className="composer-icon-btn" title="Add emoji">
            <img src={emojiIcon} alt="" aria-hidden="true" className="icon-img" />
          </button>

          <button type="button" id="composer-format" className="composer-icon-btn" title="Format text">
            Aa
          </button>

          <span id="composer-title" className="composer-title-hidden">
            {props.title}
          </span>
        </div>

        <div className="composer-header-right">
          <button
            type="button"
            id="composer-minimize"
            className="composer-icon-btn"
            title="Minimize"
            onClick={props.onMinimizeToggle}
          >
            <img src={minimizeIcon} alt="" aria-hidden="true" className="icon-img" />
          </button>

          <button
            type="button"
            id="composer-close"
            className="composer-header-link"
            title="Close"
            aria-label="Close"
            onClick={props.onClose}
          >
            <img src={closeIcon} alt="" aria-hidden="true" className="icon-img" />
          </button>
        </div>
      </div>

      {!props.minimized && (
        <div className="composer-main">
          <div className="composer-meta">
            <label className="composer-row">
              <span className="composer-label">To:</span>
              <AddressChipsInput
                fieldId="composer-to"
                placeholder="Recipients (comma or semicolon separated)"
                value={props.to}
                onChange={props.onToChange}
              />
            </label>

            <label className={`composer-row composer-row-extra ${props.extra.cc ? "" : "hidden"}`} data-field="cc">
              <span className="composer-label">Cc:</span>
              <AddressChipsInput fieldId="composer-cc" placeholder="Cc" value={props.cc} onChange={props.onCcChange} />
            </label>

            <label className={`composer-row composer-row-extra ${props.extra.bcc ? "" : "hidden"}`} data-field="bcc">
              <span className="composer-label">Bcc:</span>
              <AddressChipsInput fieldId="composer-bcc" placeholder="Bcc" value={props.bcc} onChange={props.onBccChange} />
            </label>

            <label className="composer-row">
              <span className="composer-label">Subject:</span>
              <input
                type="text"
                id="composer-subject"
                placeholder="Subject"
                value={props.subject}
                onChange={(e) => props.onSubjectChange(e.target.value)}
              />
            </label>

            <label className={`composer-row composer-row-extra ${props.extra.replyto ? "" : "hidden"}`} data-field="replyto">
              <span className="composer-label">Reply-To:</span>
              <input
                type="text"
                id="composer-replyto"
                placeholder="Reply-To"
                value={props.replyToRaw}
                onChange={(e) => props.onReplyToRawChange(e.target.value)}
              />
            </label>

            <label className={`composer-row composer-row-extra ${props.extra.priority ? "" : "hidden"}`} data-field="priority">
              <span className="composer-label">Priority:</span>
              <select
                id="composer-priority"
                value={props.priority}
                onChange={(e) => props.onPriorityChange(e.target.value as Priority)}
              >
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
              </select>
            </label>

            <label className="composer-row">
              <span className="composer-label">From:</span>
              <select id="composer-from" value={props.fromAccount} onChange={(e) => props.onFromChange(e.target.value)}>
                {!props.accounts.length && <option value="">(no accounts)</option>}
                {props.accounts.map((acc) => (
                  <option key={acc} value={acc}>
                    {acc}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <ComposerEditor value={props.html} onChange={props.onHtmlChange} />

          <ComposerAttachments 
            files={props.attachments}
            visible={props.attachments.length > 0}
            onRemove={props.onRemoveAttachmentAt} 
            onPreview={(file) => {
              const url = URL.createObjectURL(file);
              window.open(url, "_blank", "noopener,noreferrer");
              // optional cleanup (delay so the tab has time to load)
              setTimeout(() => URL.revokeObjectURL(url), 60_000);
            }}
          />
        </div>
      )}

      {!props.minimized && (
        <div className="composer-footer">
          <div id="composer-error" className={`composer-error ${props.error ? "" : "hidden"}`}>
            {props.error}
          </div>

          <button type="button" id="composer-send" className="primary" onClick={props.onSend}>
            Send
          </button>

          <div className="send-later-wrapper">
            <button
              type="button"
              id="composer-send-later-toggle"
              className="secondary"
              onClick={(e) => {
                e.stopPropagation();
                props.onToggleSendLater();
              }}
            >
              Send later ▾
            </button>

            <SendLaterMenu open={props.sendLaterOpen} onClose={props.onCloseSendLater} onPick={props.onSendLaterPick} />
          </div>
        </div>
      )}
    </div>
  );
}
