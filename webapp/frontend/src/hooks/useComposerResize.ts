// src/hooks/useComposerResize.ts
import { useEffect, useRef } from "react";

export function useComposerResize(enabled: boolean) {
  const composerRef = useRef<HTMLDivElement | null>(null);
  const zoneRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!enabled) return;

    const composerEl = composerRef.current;
    const zoneEl = zoneRef.current;
    if (!composerEl || !zoneEl) return;

    let isResizing = false;
    let startX = 0;
    let startY = 0;
    let startWidth = 0;
    let startHeight = 0;

    const minWidth = 420;
    const minHeight = 260;

    const onMove = (e: PointerEvent) => {
      if (!isResizing) return;
      const dx = startX - e.clientX;
      const dy = startY - e.clientY;
      const newWidth = Math.max(minWidth, startWidth + dx);
      const newHeight = Math.max(minHeight, startHeight + dy);
      composerEl.style.width = `${newWidth}px`;
      composerEl.style.height = `${newHeight}px`;
    };

    const onUp = () => {
      if (!isResizing) return;
      isResizing = false;
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerup", onUp);
      document.removeEventListener("pointercancel", onUp);
    };

    const onDown = (e: PointerEvent) => {
      // only left click / primary pointer
      if (e.button !== 0) return;

      e.preventDefault();
      isResizing = true;

      const rect = composerEl.getBoundingClientRect();
      startX = e.clientX;
      startY = e.clientY;
      startWidth = rect.width;
      startHeight = rect.height;

      document.addEventListener("pointermove", onMove);
      document.addEventListener("pointerup", onUp);
      document.addEventListener("pointercancel", onUp);
    };

    zoneEl.addEventListener("pointerdown", onDown);

    return () => {
      zoneEl.removeEventListener("pointerdown", onDown);
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerup", onUp);
      document.removeEventListener("pointercancel", onUp);
    };
  }, [enabled]);

  return { composerRef, zoneRef };
}
