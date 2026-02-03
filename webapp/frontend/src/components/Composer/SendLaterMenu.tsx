// src/components/Composer/SendLaterMenu.tsx
import React, { useRef } from "react";
import { useClickOutside } from "../../hooks/useClickOutside";

export type SendLaterMenuProps = {
  open: boolean;
  onClose: () => void;
  onPick: (label: string, delayKey: string) => void;
};

export default function SendLaterMenu(props: SendLaterMenuProps) {
  const menuRef = useRef<HTMLDivElement | null>(null);

  useClickOutside([menuRef], props.onClose, props.open);

  if (!props.open) return null;

  return (
    <div
      ref={menuRef}
      id="composer-send-later-menu"
      className="composer-send-later-menu"
      onClick={(e) => {
        const btn = (e.target as HTMLElement).closest("button[data-delay]") as HTMLButtonElement | null;
        if (!btn) return;
        const delayKey = btn.dataset.delay || "";
        const label = (btn.textContent || "").trim();
        props.onPick(label, delayKey);
      }}
    >
      <button type="button" data-delay="10m">
        In 10 minutes
      </button>
      <button type="button" data-delay="1h">
        In 1 hour
      </button>
      <button type="button" data-delay="tomorrow_morning">
        Tomorrow morning
      </button>
      <button type="button" data-delay="custom">
        Pick date &amp; time…
      </button>
    </div>
  );
}
