

export type EmailsHeaderProps = {
  page: number;
  pageCount: number;
  onCompose: () => void;
  onPrev: () => void;
  onNext: () => void;
};

export default function EmailsHeader(props: EmailsHeaderProps) {
  return (
    <section className="card list-header">
      <div className="list-header-top">
        <h2>Emails</h2>
        <div className="list-header-right">
          <button type="button" className="secondary" onClick={props.onCompose}>
            Compose
          </button>
          <div className="page-controls">
            <button type="button" className="secondary" onClick={props.onPrev}>
              &lt;
            </button>
            <span>
              Page {props.page} / {props.pageCount}
            </span>
            <button type="button" className="secondary" onClick={props.onNext}>
              &gt;
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
