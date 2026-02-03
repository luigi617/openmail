export type EmailsHeaderProps = {
  totalEmails: number;
  hasMore: boolean;
  isLoadingMore: boolean;
  onLoadMore: () => void;
  onCompose: () => void;
};

export default function EmailsHeader(props: EmailsHeaderProps) {
  const { totalEmails, onCompose } = props;

  const showCount = Number.isFinite(totalEmails) && totalEmails > 0;

  return (
    <section className="card list-header">
      <div className="list-header-top">
        <h2>Emails</h2>

        <div className="list-header-right">
          <button type="button" className="secondary" onClick={onCompose}>
            Compose
          </button>
          {showCount ? (
            <span className="list-count">
              {totalEmails.toLocaleString()} total
            </span>
          ) : null}

        </div>
      </div>
    </section>
  );
}
