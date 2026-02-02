import EmailsHeader from "../Middle/EmailsHeader";
import EmailList from "../Middle/EmailList";
import type { EmailOverview } from "../../types/email"

export type MiddleColumnProps = {
  page: number;
  pageCount: number;
  onPrevPage: () => void;
  onNextPage: () => void;
  onCompose: () => void;

  emails: EmailOverview[];
  emptyList: boolean;
  selectedEmailId: string | null;
  onSelectEmail: (email: EmailOverview) => void;

  getEmailId: (email: EmailOverview) => string;
  getColorForEmail: (email: EmailOverview) => string;
};

export default function MiddleColumn(props: MiddleColumnProps) {
  return (
    <>
      <EmailsHeader
        page={props.page}
        pageCount={props.pageCount}
        onPrev={props.onPrevPage}
        onNext={props.onNextPage}
        onCompose={props.onCompose}
      />

      <section className="card list-container">
        <EmailList
          emails={props.emails}
          selectedEmailId={props.selectedEmailId}
          getColorForEmail={props.getColorForEmail}
          getEmailId={props.getEmailId}
          onSelectEmail={props.onSelectEmail}
        />
        <div className={`empty-state ${props.emptyList ? "" : "hidden"}`}>
          No emails match the current filters.
        </div>
      </section>
    </>
  );
}
