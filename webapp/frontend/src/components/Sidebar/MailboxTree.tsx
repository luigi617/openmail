// src/components/Sidebar/MailboxTree.tsx
import { useMemo, useState } from 'react';
import type { MailboxData } from '../../types/email';
import { getMailboxDisplayName } from '../../utils/emailFormat';

export type MailboxTreeProps = {
  mailboxData: MailboxData;
  currentMailbox: string;
  filterAccounts: string[];
  onSelectAllInboxes: () => void;
  onSelectMailbox: (account: string, mailbox: string) => void;
};

export default function MailboxTree(props: MailboxTreeProps) {
  const { mailboxData, currentMailbox, filterAccounts, onSelectAllInboxes, onSelectMailbox } =
    props;

  const [collapsedAccounts, setCollapsedAccounts] = useState<Record<string, boolean>>({});

  const entries = useMemo(() => Object.entries(mailboxData || {}), [mailboxData]);

  const activeAccounts = useMemo(() => new Set(filterAccounts || []), [filterAccounts]);

  const allInboxesUnseen = useMemo(() => {
    const data = mailboxData || {};
    const accounts = Object.keys(data);

    return accounts.reduce((sum, account) => {
      const mailboxesObj = data[account] || {};
      const inboxStatus = mailboxesObj['INBOX'];
      const unseen = Number(inboxStatus?.unseen ?? 0);
      return sum + unseen;
    }, 0);
  }, [mailboxData]); // ✅ removed filterAccounts (unused)

  return (
    <div id="mailbox-list" className="mailbox-list">
      {/* All inboxes */}
      <div className="mailbox-group">
        <div
          className={`mailbox-item mailbox-item-all ${
            !activeAccounts.size && currentMailbox === 'INBOX' ? 'active' : ''
          }`}
          data-mailbox="INBOX"
          data-account=""
          onClick={onSelectAllInboxes}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') onSelectAllInboxes();
          }}
        >
          <span className="mailbox-dot" />
          <span className="mailbox-name">All inboxes</span>

          {allInboxesUnseen > 0 ? (
            <span className="mailbox-badge" aria-label={`${allInboxesUnseen} unread`}>
              {allInboxesUnseen}
            </span>
          ) : null}
        </div>
      </div>

      {!entries.length ? (
        <div>No mailboxes available.</div>
      ) : (
        entries.map(([account, mailboxesObj]) => {
          const isCollapsed = !!collapsedAccounts[account];

          // mailboxesObj: Record<mailboxName, status>
          const mailboxItems = Object.entries(mailboxesObj || {})
            .map(([name, status]) => ({
              name,
              unseen: Number(status?.unseen ?? 0),
              messages: Number(status?.messages ?? 0),
            }))
            .sort((a, b) => {
              if (a.name === 'INBOX' && b.name !== 'INBOX') return -1;
              if (b.name === 'INBOX' && a.name !== 'INBOX') return 1;
              return a.name.localeCompare(b.name);
            });

          return (
            <div key={account} className="mailbox-group">
              <button
                type="button"
                className={`mailbox-account ${isCollapsed ? 'collapsed' : ''}`}
                onClick={() => setCollapsedAccounts((s) => ({ ...s, [account]: !s[account] }))}
              >
                <span className="mailbox-account-chev">▾</span>
                <span>{account}</span>
              </button>

              <div className={`mailbox-group-items ${isCollapsed ? 'collapsed' : ''}`}>
                {mailboxItems.map(({ name, unseen }) => {
                  // Old rule: when no filterAccounts, only “All inboxes” is active
                  const isActive =
                    name === currentMailbox &&
                    activeAccounts.size > 0 &&
                    activeAccounts.has(account);

                  return (
                    <div
                      key={`${account}:${name}`}
                      className={`mailbox-item ${isActive ? 'active' : ''}`}
                      data-mailbox={name}
                      data-account={account}
                      onClick={() => onSelectMailbox(account, name)}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') onSelectMailbox(account, name);
                      }}
                    >
                      <span className="mailbox-dot" />
                      <span className="mailbox-name">{getMailboxDisplayName(name)}</span>

                      {unseen > 0 ? (
                        <span className="mailbox-badge" aria-label={`${unseen} unread`}>
                          {unseen}
                        </span>
                      ) : null}
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
