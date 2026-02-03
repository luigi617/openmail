// src/components/Composer/ComposerExtraMenu.tsx
import React, { useRef } from "react";
import { useClickOutside } from "../../hooks/useClickOutside";
import type { ComposerExtraFieldKey } from "../../types/composer";

export type ComposerExtraMenuProps = {
  open: boolean;
  onClose: () => void;
  state: Record<ComposerExtraFieldKey, boolean>;
  onToggle: (k: ComposerExtraFieldKey) => void;
};

export default function ComposerExtraMenu(props: ComposerExtraMenuProps) {
  const menuRef = useRef<HTMLDivElement | null>(null);

  useClickOutside([menuRef], props.onClose, props.open);

  if (!props.open) return null;

  return (
    <div ref={menuRef} id="composer-extra-menu" className="composer-extra-menu">
      <label className="composer-extra-item">
        <input type="checkbox" checked={!!props.state.cc} onChange={() => props.onToggle("cc")} />
        Cc
      </label>

      <label className="composer-extra-item">
        <input type="checkbox" checked={!!props.state.bcc} onChange={() => props.onToggle("bcc")} />
        Bcc
      </label>

      <label className="composer-extra-item">
        <input type="checkbox" checked={!!props.state.replyto} onChange={() => props.onToggle("replyto")} />
        Reply-To
      </label>

      <label className="composer-extra-item">
        <input type="checkbox" checked={!!props.state.priority} onChange={() => props.onToggle("priority")} />
        Priority
      </label>
    </div>
  );
}
