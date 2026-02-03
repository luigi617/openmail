// src/hooks/useClickOutside.ts
import { useEffect, type RefObject } from 'react';

export function useClickOutside(
  refs: ReadonlyArray<RefObject<HTMLElement | null>>,
  onOutside: () => void,
  enabled: boolean
) {
  useEffect(() => {
    if (!enabled) return;

    const handler = (ev: PointerEvent) => {
      const target = ev.target as Node | null;
      if (!target) return;

      const inside = refs.some((r) => {
        const el = r.current;
        return el ? el.contains(target) : false;
      });

      if (!inside) onOutside();
    };

    document.addEventListener('pointerdown', handler, { capture: true });
    return () => {
      document.removeEventListener('pointerdown', handler, { capture: true } as any);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, onOutside]);
}
