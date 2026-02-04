// src/components/Sidebar/MailboxesCard.tsx
import MailboxTree from './MailboxTree';
import type { MailboxData } from '../../types/email';

export type MailboxesCardProps = {
  mailboxData: MailboxData;
  currentMailbox: string;
  filterAccounts: string[];
  onSelectAllInboxes: () => void;
  onSelectMailbox: (account: string, mailbox: string) => void;

  onManageAccounts: () => void; // NEW
};

export default function MailboxesCard(props: MailboxesCardProps) {
  return (
    <section className="card">
      <div className="mailboxes-header">
        <h2>Mailboxes</h2>
        <button className="secondary" onClick={props.onManageAccounts}>
          Accounts
        </button>
      </div>

      <MailboxTree {...props} />
    </section>
  );
}
