

export type EmailsHeaderProps = {
  page: number;
  pageCount: number;
  onCompose: () => void;
  onPrev: () => void;
  onNext: () => void;
};

export default function EmailsHeader(props: EmailsHeaderProps) {
  const { page, pageCount, onCompose, onPrev, onNext } = props;

  return (
    <section className="card list-header">
      <div className="list-header-top">
        <h2>Emails</h2>
        <div className="list-header-right">
          <button type="button" className="secondary" onClick={onCompose}>
            Compose
          </button>

          <div className="page-controls">
            {page > 1 && (
              <button type="button" className="secondary" onClick={onPrev}>
                &lt;
              </button>
            )}

            <span>
              Page {page} / {pageCount}
            </span>

            {page < pageCount && (
              <button type="button" className="secondary" onClick={onNext}>
                &gt;
              </button>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
