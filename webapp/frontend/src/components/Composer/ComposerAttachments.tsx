// src/components/Composer/ComposerAttachments.tsx
import React from "react";
import closeIcon from "@/assets/svg/close.svg";

export type ComposerAttachmentsProps = {
  files: File[];
  visible: boolean;
  onRemove: (idx: number) => void;
  onPreview: (file: File) => void;
};

export default function ComposerAttachments(props: ComposerAttachmentsProps) {
  return (
    <div className={`composer-attachments ${props.visible ? "" : "hidden"}`}>
      {props.files.map((f, idx) => (
        <div key={`${f.name}-${idx}`} className="attachment-pill" role="group">
          <button
            type="button"
            className="attachment-pill-main"
            onClick={() => props.onPreview(f)}
            title="Preview attachment"
          >
            {f.name}
          </button>

          <button
            type="button"
            className="attachment-pill-remove"
            title="Remove attachment"
            onClick={(e) => {
              e.stopPropagation();
              props.onRemove(idx);
            }}
          >
            <img src={closeIcon} alt="" aria-hidden="true" className="icon-img" />
          </button>
        </div>
      ))}
    </div>
  );
}
