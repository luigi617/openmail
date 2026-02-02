// src/App.tsx
import { useMemo, useState, useEffect } from "react";
import Layout from "./components/Layout/Layout";
import Composer from "./components/Composer/Composer";
import AppAlertModal from "./components/Modal/AppAlertModal";

import { useEmailAppCore } from "./hooks/useEmailApp";
import { useAppModal } from "./hooks/useAppModal";
import { useComposer } from "./hooks/useComposer";
import { useDetailActions } from "./hooks/useDetailActions";

import { applyTheme } from "./theme/applyTheme";
import { onSystemThemeChange } from "./theme/systemTheme";


export default function App() {
  const core = useEmailAppCore();
  const modal = useAppModal();

  useEffect(() => {
    applyTheme("system");
    return onSystemThemeChange(() => applyTheme("system"));
  }, []);

  // local UI toggles for composer menus
  const [composerExtraMenuOpen, setComposerExtraMenuOpen] = useState(false);
  const [sendLaterOpen, setSendLaterOpen] = useState(false);

  const detailActions = useDetailActions({
    getSelectedRef: core.getSelectedRef,
    refreshOverview: () => core.fetchOverview(null),
    confirm: modal.confirm,
    setDetailError: core.setDetailError,
  });

  const composer = useComposer({
    mailboxData: core.mailboxData,
    selectedOverview: core.selectedOverview,
    selectedMessage: core.selectedMessage,
    getSelectedRef: core.getSelectedRef,
    showCloseConfirm: ({ onSaveDraft, onDiscard }) => {
      modal.show({
        title: "Close message?",
        message: "You have unsent changes. Do you want to save this message as a draft?",
        buttons: [
          {
            id: 1,
            label: "Save draft",
            variant: "primary",
            onClick: async () => {
              await onSaveDraft();
              modal.close();
            },
          },
          {
            id: 2,
            label: "Discard",
            variant: "secondary",
            onClick: () => {
              onDiscard();
              modal.close();
            },
          },
          {
            id: 3,
            label: "Cancel",
            variant: "secondary",
            onClick: () => modal.close(),
          },
        ],
      });
    },
  });

  const composerTitle = useMemo(() => {
    if (!composer.state.open) return "";
    switch (composer.state.mode) {
      case "compose":
        return "New message";
      case "reply":
        return "Reply";
      case "reply_all":
        return "Reply all";
      case "forward":
        return "Forward";
      default:
        return "Message";
    }
  }, [composer.state.open, composer.state.mode]);

  return (
    <>
      <Layout
        sidebar={{
          searchQuery: core.searchText,
          onSearchQueryChange: core.setSearchText,
          onSearch: () => {
            core.applySearch();
          },

          mailboxData: core.mailboxData,
          currentMailbox: core.currentMailbox,
          filterAccounts: core.filterAccounts,

          onSelectAllInboxes: () => {
            core.setCurrentMailbox("INBOX");
            core.setFilterAccounts([]);
          },
          onSelectMailbox: (account: string, mailbox: string) => {
            core.setCurrentMailbox(mailbox);
            core.setFilterAccounts([account]);
          },

          legendAccounts: core.legendAccounts,
          legendColorMap: core.legendColorMap,

          onToggleLegendAccount: (acc: string) => {
            core.setFilterAccounts((prev) => {
              const set = new Set(prev);
              if (set.has(acc)) set.delete(acc);
              else set.add(acc);
              return Array.from(set);
            });
          },
        }}
        middle={{
          page: core.currentPage,
          pageCount: core.totalPages,
          onPrevPage: () => void core.fetchOverview("prev"),
          onNextPage: () => void core.fetchOverview("next"),
          onCompose: () => {
            setComposerExtraMenuOpen(false);
            setSendLaterOpen(false);
            composer.open("compose");
          },

          emails: core.emails,
          emptyList: core.emails.length == 0,
          selectedEmailId: core.selectedId,

          onSelectEmail: (email) => {
            core.selectEmail(email);
          },

          getEmailId: core.helpers.getEmailId,
          getColorForEmail: core.helpers.getColorForEmail,
        }}
        detail={{
          selectedOverview: core.selectedOverview,
          selectedMessage: core.selectedMessage,
          mailboxData: core.mailboxData,
          currentMailbox: core.currentMailbox,

          detailError: core.detailError,
          getColorForEmail: core.helpers.getColorForEmail,

          onArchive: detailActions.archiveSelected,
          onDelete: detailActions.deleteSelected,
          onReply: () => {
            setComposerExtraMenuOpen(false);
            setSendLaterOpen(false);
            composer.open("reply");
          },
          onReplyAll: () => {
            setComposerExtraMenuOpen(false);
            setSendLaterOpen(false);
            composer.open("reply_all");
          },
          onForward: () => {
            setComposerExtraMenuOpen(false);
            setSendLaterOpen(false);
            composer.open("forward");
          },
          onMove: (destinationMailbox: string) => detailActions.moveSelected(destinationMailbox),
        }}
      />

      <Composer
        open={composer.state.open}
        onClose={() => {
          composer.requestClose();
          setComposerExtraMenuOpen(false);
          setSendLaterOpen(false);
        }}
        title={composerTitle}
        minimized={composer.state.minimized}
        onMinimizeToggle={composer.minimizeToggle}
        extra={composer.state.extra}
        onToggleExtraField={composer.toggleExtraField}
        to={composer.state.to}
        cc={composer.state.cc}
        bcc={composer.state.bcc}
        onToChange={composer.setTo}
        onCcChange={composer.setCc}
        onBccChange={composer.setBcc}
        subject={composer.state.subject}
        onSubjectChange={composer.setSubject}
        replyToRaw={composer.state.replyToRaw}
        onReplyToRawChange={composer.setReplyToRaw}
        priority={composer.state.priority}
        onPriorityChange={composer.setPriority}
        fromAccount={composer.state.fromAccount}
        accounts={composer.accounts}
        onFromChange={composer.setFromAccount}
        html={composer.state.html}
        onHtmlChange={composer.setHtml}
        attachments={composer.state.attachments}
        onAddAttachments={composer.addAttachments}
        onRemoveAttachmentAt={composer.removeAttachmentAt}
        error={composer.state.error}
        onSend={composer.send}
        sendLaterOpen={sendLaterOpen}
        onToggleSendLater={() => setSendLaterOpen((v) => !v)}
        onCloseSendLater={() => setSendLaterOpen(false)}
        extraMenuOpen={composerExtraMenuOpen}
        onToggleExtraMenu={() => setComposerExtraMenuOpen((v) => !v)}
        onCloseExtraMenu={() => setComposerExtraMenuOpen(false)}
        onSendLaterPick={(label) => {
          setSendLaterOpen(false);
          modal.show({
            title: "Send later",
            message: `"Send later" (${label}) is not wired to the backend yet.`,
            buttons: [{ id: 1, label: "OK", variant: "primary", onClick: () => modal.close() }],
          });
        }}
      />

      <AppAlertModal state={modal.modal} onClose={modal.close} />
    </>
  );
}
