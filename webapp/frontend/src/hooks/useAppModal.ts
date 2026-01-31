// src/hooks/useAppModal.ts
import { useCallback, useState } from "react";
import type { AppModalButton, AppModalState } from "../types/modal";

export function useAppModal() {
  const [modal, setModal] = useState<AppModalState>({
    open: false,
    title: "Notice",
    message: "",
    buttons: [],
  });

  const close = useCallback(() => {
    setModal((m) => ({ ...m, open: false }));
  }, []);

  const show = useCallback(
    (args: { title?: string; message?: string; buttons?: AppModalButton[] } | string) => {
      const cfg = typeof args === "string" ? { message: args } : args;

      setModal({
        open: true,
        title: cfg.title ?? "Notice",
        message: cfg.message ?? "",
        buttons:
          cfg.buttons && cfg.buttons.length
            ? cfg.buttons
            : [{ id: 1, label: "OK", variant: "primary", onClick: close }],
      });
    },
    [close]
  );

  const confirm = useCallback(
    (args: {
      title?: string;
      message?: string;
      confirmLabel?: string;
      cancelLabel?: string;
      confirmVariant?: "primary" | "secondary";
      cancelVariant?: "primary" | "secondary";
    }) => {
      return new Promise<boolean>((resolve) => {
        show({
          title: args.title ?? "Confirm",
          message: args.message ?? "",
          buttons: [
            {
              id: 1,
              label: args.cancelLabel ?? "Cancel",
              variant: args.cancelVariant ?? "secondary",
              onClick: () => {
                close();
                resolve(false);
              },
            },
            {
              id: 2,
              label: args.confirmLabel ?? "OK",
              variant: args.confirmVariant ?? "primary",
              onClick: () => {
                close();
                resolve(true);
              },
            },
          ],
        });
      });
    },
    [show, close]
  );

  return { modal, setModal, show, confirm, close };
}
