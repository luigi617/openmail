// src/hooks/useDetailActions.ts
import { useCallback } from "react";
import { EmailApi } from "../api/emailApi";
import type { EmailRef } from "../types/shared";

export function useDetailActions(args: {
  getSelectedRef: () => EmailRef | null;
  refreshOverview: () => Promise<void> | void;
  confirm: (cfg: {
    title?: string;
    message?: string;
    confirmLabel?: string;
    cancelLabel?: string;
    confirmVariant?: "primary" | "secondary";
    cancelVariant?: "primary" | "secondary";
  }) => Promise<boolean>;
  setDetailError: (msg: string) => void;
}) {
  const archiveSelected = useCallback(async () => {
    args.setDetailError("");
    const ref = args.getSelectedRef();
    if (!ref) {
      args.setDetailError("No email selected to archive.");
      return;
    }

    const ok = await args.confirm({
      title: "Archive email",
      message: "Archive this email?",
      confirmLabel: "Archive",
      confirmVariant: "primary",
      cancelLabel: "Cancel",
      cancelVariant: "secondary",
    });
    if (!ok) return;

    try {
      await EmailApi.archiveEmail(ref);
      await args.refreshOverview();
    } catch (e) {
      console.error("Error archiving:", e);
      args.setDetailError("Error archiving email. Please try again.");
    }
  }, [args]);

  const deleteSelected = useCallback(async () => {
    args.setDetailError("");
    const ref = args.getSelectedRef();
    if (!ref) {
      args.setDetailError("No email selected to delete.");
      return;
    }

    const ok = await args.confirm({
      title: "Delete email",
      message: "Permanently delete this email?",
      confirmLabel: "Delete",
      confirmVariant: "primary",
      cancelLabel: "Cancel",
      cancelVariant: "secondary",
    });
    if (!ok) return;

    try {
      await EmailApi.deleteEmail(ref);
      await args.refreshOverview();
    } catch (e) {
      console.error("Error deleting:", e);
      args.setDetailError("Error deleting email. Please try again.");
    }
  }, [args]);

  const moveSelected = useCallback(
    async (destinationMailbox: string) => {
      args.setDetailError("");
      const ref = args.getSelectedRef();
      if (!ref) {
        args.setDetailError("No email selected to move.");
        return;
      }
      if (!destinationMailbox || destinationMailbox === ref.mailbox) return;

      try {
        await EmailApi.moveEmail({ ...ref, destinationMailbox });
        await args.refreshOverview();
      } catch (e) {
        console.error("Error moving email:", e);
        args.setDetailError("Error moving email. Please try again.");
      }
    },
    [args]
  );

  return { archiveSelected, deleteSelected, moveSelected };
}
