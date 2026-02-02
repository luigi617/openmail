// src/components/Sidebar/MailboxesCard.tsx
import MailboxTree from "./MailboxTree";
import type { MailboxData } from "../../types/email";

export type MailboxesCardProps = {
  mailboxData: MailboxData;
  currentMailbox: string;
  filterAccounts: string[];
  onSelectAllInboxes: () => void;
  onSelectMailbox: (account: string, mailbox: string) => void;
};

export default function MailboxesCard(props: MailboxesCardProps) {
  return (
    <section className="card">
      <h2>Mailboxes</h2>
      <MailboxTree {...props} />
    </section>
  );
}
