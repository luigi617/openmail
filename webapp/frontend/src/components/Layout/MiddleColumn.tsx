import EmailsHeader from "../Middle/EmailsHeader";
import EmailList from "../Middle/EmailList";
import type { EmailOverview } from "../../types/email";
import { useEffect, useRef, useCallback } from "react";

export type MiddleColumnProps = {
  hasMore: boolean;
  isLoadingMore: boolean;
  totalEmails: number;

  onLoadMore: () => void;
  onCompose: () => void;

  emails: EmailOverview[];
  emptyList: boolean;
  selectedEmailId: string | null;
  onSelectEmail: (email: EmailOverview) => void;

  getEmailId: (email: EmailOverview) => string;
  getColorForEmail: (email: EmailOverview) => string;
};

export default function MiddleColumn(props: MiddleColumnProps) {
  const listRef = useRef<HTMLDivElement | null>(null);      // <-- scroll container (.email-list)
  const sentinelRef = useRef<HTMLDivElement | null>(null);  // <-- bottom sentinel

  const maybeLoadMore = useCallback(() => {
    if (!props.hasMore) return;
    if (props.isLoadingMore) return;
    if (props.emptyList) return;
    props.onLoadMore();
  }, [props.hasMore, props.isLoadingMore, props.emptyList, props.onLoadMore]);

  useEffect(() => {
    const rootEl = listRef.current;
    const target = sentinelRef.current;
    if (!rootEl || !target) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (entry?.isIntersecting) {
          maybeLoadMore();
        }
      },
      {
        root: rootEl,           // IMPORTANT: observe within the scrolling email list
        threshold: 0,
        rootMargin: "200px",    // prefetch a bit before hitting the absolute bottom
      }
    );

    observer.observe(target);
    return () => observer.disconnect();
  }, [maybeLoadMore, props.emails.length]); // re-run when list grows so IO recalculates

  return (
    <>
      <EmailsHeader
        totalEmails={props.totalEmails}
        hasMore={props.hasMore}
        isLoadingMore={props.isLoadingMore}
        onLoadMore={props.onLoadMore}
        onCompose={props.onCompose}
      />

      <section className="card list-container">
        <EmailList
          emails={props.emails}
          selectedEmailId={props.selectedEmailId}
          getColorForEmail={props.getColorForEmail}
          getEmailId={props.getEmailId}
          onSelectEmail={props.onSelectEmail}
          listRef={listRef}
          sentinelRef={sentinelRef}
          showLoadingMore={props.isLoadingMore}
          showEnd={!props.hasMore && props.emails.length > 0}
          emptyList={props.emptyList}
        />
      </section>
    </>
  );
}
