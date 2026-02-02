// src/components/Sidebar/MailboxTree.tsx
import { useMemo, useState } from "react";
import type { MailboxData } from "../../types/email";
import { getMailboxDisplayName } from "../../utils/emailFormat";

export type MailboxTreeProps = {
  mailboxData: MailboxData;
  currentMailbox: string;
  filterAccounts: string[];
  onSelectAllInboxes: () => void;
  onSelectMailbox: (account: string, mailbox: string) => void;
};

export default function MailboxTree(props: MailboxTreeProps) {
  const [collapsedAccounts, setCollapsedAccounts] = useState<Record<string, boolean>>({});

  const entries = useMemo(() => Object.entries(props.mailboxData || {}), [props.mailboxData]);
  const activeAccounts = useMemo(() => new Set(props.filterAccounts || []), [props.filterAccounts]);

  return (
    <div id="mailbox-list" className="mailbox-list">
      {/* All inboxes */}
      <div className="mailbox-group">
        <div
          className={`mailbox-item mailbox-item-all ${
            !activeAccounts.size && props.currentMailbox === "INBOX" ? "active" : ""
          }`}
          data-mailbox="INBOX"
          data-account=""
          onClick={props.onSelectAllInboxes}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") props.onSelectAllInboxes();
          }}
        >
          <span className="mailbox-dot" />
          <span>All inboxes</span>
        </div>
      </div>

      {!entries.length ? (
        <div>No mailboxes available.</div>
      ) : (
        entries.map(([account, mailboxes]) => {
          const isCollapsed = !!collapsedAccounts[account];

          return (
            <div key={account} className="mailbox-group">
              <button
                type="button"
                className={`mailbox-account ${isCollapsed ? "collapsed" : ""}`}
                onClick={() => setCollapsedAccounts((s) => ({ ...s, [account]: !s[account] }))}
              >
                <span className="mailbox-account-chev">▾</span>
                <span>{account}</span>
              </button>

              <div className={`mailbox-group-items ${isCollapsed ? "collapsed" : ""}`}>
                {(mailboxes || []).map((m) => {
                  // Old rule: when no filterAccounts, only “All inboxes” is active
                  const isActive =
                    m === props.currentMailbox && activeAccounts.size > 0 && activeAccounts.has(account);

                  return (
                    <div
                      key={`${account}:${m}`}
                      className={`mailbox-item ${isActive ? "active" : ""}`}
                      data-mailbox={m}
                      data-account={account}
                      onClick={() => props.onSelectMailbox(account, m)}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") props.onSelectMailbox(account, m);
                      }}
                    >
                      <span className="mailbox-dot" />
                      <span>{getMailboxDisplayName(m)}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })
      )}
    </div>
  );
}
