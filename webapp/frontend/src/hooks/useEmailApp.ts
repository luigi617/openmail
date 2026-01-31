// src/hooks/useEmailApp.ts
import { useCallback, useEffect, useMemo, useState } from "react";
import { EmailApi } from "../api/emailApi";
import type { EmailRef } from "../types/shared";
import type { MailboxData, EmailOverview, EmailMessage } from "../types/email";
import {
  buildColorMap,
  findAccountForEmail,
  getColorForEmail,
  getEmailId,
} from "../utils/emailFormat";

export function useEmailAppCore() {
  // mailbox state
  const [mailboxData, setMailboxData] = useState<MailboxData>({});
  const [currentMailbox, setCurrentMailbox] = useState<string>("INBOX");

  // legend filter (accounts)
  const [filterAccounts, setFilterAccounts] = useState<string[]>([]);

  // overview + paging (cursor-based)
  const [emails, setEmails] = useState<EmailOverview[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [prevCursor, setPrevCursor] = useState<string | null>(null);

  const pageSize = 50;
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [totalPages, setTotalPages] = useState<number>(1);

  // search
  const [searchText, setSearchText] = useState<string>("");

  // selection + detail
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedOverview, setSelectedOverview] = useState<EmailOverview | null>(null);
  const [selectedMessage, setSelectedMessage] = useState<EmailMessage | null>(null);

  // errors (inline)
  const [listError, setListError] = useState<string>("");
  const [detailError, setDetailError] = useState<string>("");

  // derived: color map (single source of truth)
  const colorMap = useMemo(() => buildColorMap(emails, mailboxData), [emails, mailboxData]);

  // derived: filtered list (keep it simple & fast)
  const filteredEmails = useMemo(() => {
    const q = searchText.trim().toLowerCase();
    if (!q) return emails;

    return emails.filter((e) => {
      const subject = (e.subject || "").toLowerCase();
      const from = `${e.from_email?.name ?? ""} ${e.from_email?.email ?? ""}`.toLowerCase();
      return subject.includes(q) || from.includes(q);
    });
  }, [emails, searchText]);

  const emptyList = filteredEmails.length === 0;

  const getSelectedRef = useCallback((): EmailRef | null => {
    const ov = selectedOverview;
    if (!ov) return null;

    const account = ov.ref.account;
    const mailbox = ov.ref.mailbox ?? currentMailbox;
    const uid = ov.ref.uid;

    if (!account || !mailbox || uid == null) return null;

    return {
      account: String(account),
      mailbox: String(mailbox),
      uid: uid,
    };
  }, [selectedOverview, currentMailbox]);

  const fetchMailboxes = useCallback(async () => {
    try {
      setListError("");
      // backend returns: { [account: string]: string[] }
      const data = (await EmailApi.getMailboxes()) as unknown as MailboxData;
      setMailboxData(data || {});
    } catch (e) {
      console.error("Error fetching mailboxes:", e);
      setListError("Failed to fetch mailboxes.");
    }
  }, []);

  const fetchOverview = useCallback(
    async (direction: null | "next" | "prev" = null) => {
      try {
        setListError("");

        // Decide cursor usage
        let useCursor: string | undefined;

        if (direction === "next") {
          if (!nextCursor) return; // no-op if no next page
          useCursor = nextCursor;
        } else if (direction === "prev") {
          if (!prevCursor) return; // no-op if no prev page
          useCursor = prevCursor;
        } else {
          // fresh load
          useCursor = undefined;
          setCurrentPage(1);
        }

        const payload = await EmailApi.getOverview<EmailOverview>({
          mailbox: currentMailbox,
          limit: pageSize,
          cursor: useCursor,
          // apply account filter only on a fresh load (cursor pagination should keep its own server-side context)
          accounts: useCursor ? undefined : filterAccounts.length ? [...filterAccounts] : undefined,
        });

        const list = Array.isArray(payload.data) ? payload.data : [];
        const meta = payload.meta ?? {};

        setEmails(list);

        // reset selection on new list
        setSelectedId(null);
        setSelectedOverview(null);
        setSelectedMessage(null);
        setDetailError("");

        setNextCursor(meta.next_cursor ?? null);
        setPrevCursor(meta.prev_cursor ?? null);

        // page counter
        setCurrentPage((prev) => {
          if (direction === "next") return prev + 1;
          if (direction === "prev") return Math.max(1, prev - 1);
          return 1;
        });

        // total pages (if backend provides total)
        const total = typeof meta.total_count === "number" ? meta.total_count : undefined;
        if (typeof total === "number" && total >= 0) {
          setTotalPages(Math.max(1, Math.ceil(total / pageSize)));
        } else {
          // unknown total with cursor paging: keep whatever we had (at least 1)
          setTotalPages((p) => Math.max(1, p || 1));
        }
      } catch (e) {
        console.error("Error fetching overview:", e);
        setEmails([]);
        setListError("Failed to fetch emails.");
      }
    },
    [currentMailbox, pageSize, nextCursor, prevCursor, filterAccounts]
  );

  const fetchEmailMessage = useCallback(
    async (overview: EmailOverview) => {
      const account = overview.ref.account;
      const mailbox = overview.ref.mailbox ?? currentMailbox;
      const uid = overview.ref.uid;

      if (!account || !mailbox || uid == null) {
        setSelectedMessage(null);
        return;
      }

      try {
        setDetailError("");
        setSelectedMessage(null);

        const msg = await EmailApi.getEmail<EmailMessage>({
          account: String(account),
          mailbox: String(mailbox),
          uid: uid,
        });

        setSelectedMessage(msg);
      } catch (e) {
        console.error("Error fetching email detail:", e);
        setDetailError("Failed to load full email content.");
        setSelectedMessage(null);
      }
    },
    [currentMailbox]
  );

  // initial: mailboxes
  useEffect(() => {
    void fetchMailboxes();
  }, [fetchMailboxes]);


  const selectEmail = useCallback(
    (email: EmailOverview) => {
      const id = getEmailId(email);
      setSelectedId(id || null);
      setSelectedOverview(email);
      setSelectedMessage(null);
      void fetchEmailMessage(email);
    },
    [fetchEmailMessage]
  );

  const legendAccounts = useMemo(() => Object.keys(mailboxData || {}), [mailboxData]);

  const helpers = useMemo(() => {
    return {
      getEmailId: (e: EmailOverview) => getEmailId(e),
      findAccountForEmail: (e: EmailOverview) => findAccountForEmail(e, mailboxData),
      getColorForEmail: (e: EmailOverview) => getColorForEmail(e, mailboxData, colorMap),
    };
  }, [mailboxData, colorMap]);

  return {
    // mailbox
    mailboxData,
    currentMailbox,
    setCurrentMailbox,

    // legend filter
    filterAccounts,
    setFilterAccounts,

    // overview
    emails,
    filteredEmails,
    emptyList,
    pageSize,
    currentPage,
    totalPages,
    nextCursor,
    prevCursor,

    // search
    searchText,
    setSearchText,

    // selection + detail
    selectedId,
    selectedOverview,
    selectedMessage,
    getSelectedRef,
    selectEmail,

    // errors
    listError,
    detailError,
    setDetailError,

    // actions
    fetchMailboxes,
    fetchOverview,

    // legend
    legendAccounts,
    legendColorMap: colorMap,

    // helpers (id/color/account)
    helpers,
  };
}
