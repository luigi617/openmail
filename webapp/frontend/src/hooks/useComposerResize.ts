// src/hooks/useComposerResize.ts
import { useEffect, useRef } from 'react';

export function useComposerResize(enabled: boolean) {
  const composerRef = useRef<HTMLDivElement | null>(null);
  const zoneRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const composerEl = composerRef.current;
    const zoneEl = zoneRef.current;
    if (!composerEl) return;

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
      document.removeEventListener('pointermove', onMove);
      document.removeEventListener('pointerup', onUp);
      document.removeEventListener('pointercancel', onUp);
    };

    const onDown = (e: PointerEvent) => {
      // only left click / primary pointer
      if (!enabled) return;
      if (e.button !== 0) return;

      e.preventDefault();
      isResizing = true;

      const rect = composerEl.getBoundingClientRect();
      startX = e.clientX;
      startY = e.clientY;
      startWidth = rect.width;
      startHeight = rect.height;

      document.addEventListener('pointermove', onMove);
      document.addEventListener('pointerup', onUp);
      document.addEventListener('pointercancel', onUp);
    };

    // When disabled (minimized), stop resizing and clear inline sizing so
    // minimized CSS can take over (prevents "blank composer" after resize).
    if (!enabled) {
      // stop any in-progress drag
      onUp();
      // clear inline styles applied by resizing
      composerEl.style.width = '';
      composerEl.style.height = '';
      return;
    }

    if (!zoneEl) return;
    zoneEl.addEventListener('pointerdown', onDown);

    return () => {
      onUp();
      zoneEl?.removeEventListener('pointerdown', onDown);
      document.removeEventListener('pointermove', onMove);
      document.removeEventListener('pointerup', onUp);
      document.removeEventListener('pointercancel', onUp);
    };
  }, [enabled]);

  return { composerRef, zoneRef };
}
