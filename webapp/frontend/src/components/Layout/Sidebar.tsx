// src/components/Layout/Sidebar.tsx
import SearchCard from '../Sidebar/SearchCard';
import MailboxesCard from '../Sidebar/MailboxesCard';
import LegendCard from '../Sidebar/LegendCard';
import type { MailboxData } from '../../types/email';

export type SidebarProps = {
  searchQuery: string;
  onSearch: (v: string) => void;

  mailboxData: MailboxData;
  currentMailbox: string;
  filterAccounts: string[];
  onSelectAllInboxes: () => void;
  onSelectMailbox: (account: string, mailbox: string) => void;

  legendAccounts: string[];
  legendColorMap: Record<string, string>;
  onToggleLegendAccount: (account: string) => void;
};

export default function Sidebar(props: SidebarProps) {
  return (
    <>
      <SearchCard searchQuery={props.searchQuery} onSearch={props.onSearch} />

      <MailboxesCard
        mailboxData={props.mailboxData}
        currentMailbox={props.currentMailbox}
        filterAccounts={props.filterAccounts}
        onSelectAllInboxes={props.onSelectAllInboxes}
        onSelectMailbox={props.onSelectMailbox}
      />

      <LegendCard
        accounts={props.legendAccounts}
        colorMap={props.legendColorMap}
        activeAccounts={props.filterAccounts}
        onToggleAccount={props.onToggleLegendAccount}
      />
    </>
  );
}
