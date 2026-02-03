// src/hooks/useEmailApp.ts
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { EmailApi } from "../api/emailApi";
import type { EmailRef } from "../types/shared";
import type { MailboxData, EmailOverview, EmailMessage } from "../types/email";
import {
  buildColorMap,
  findAccountForEmail,
  getColorForEmail,
  getEmailId,
} from "../utils/emailFormat";

const DEFAULT_MAILBOX = "INBOX";

function parseAccountsParam(value: string | null): string[] {
  if (!value) return [];
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function toAccountsParam(accounts: string[]): string | null {
  const cleaned = (accounts || []).map((s) => String(s).trim()).filter(Boolean);
  return cleaned.length ? cleaned.join(",") : null;
}

function sameArray(a: string[], b: string[]) {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
}

function mergeUniqueById(prev: EmailOverview[], next: EmailOverview[]) {
    const seen = new Set<string>();
    const out: EmailOverview[] = [];

    for (const e of prev) {
      const id = getEmailId(e);
      if (!id) continue;
      if (!seen.has(id)) {
        seen.add(id);
        out.push(e);
      }
    }

    for (const e of next) {
      const id = getEmailId(e);
      if (!id) continue;
      if (!seen.has(id)) {
        seen.add(id);
        out.push(e);
      }
    }

    return out;
}

export function useEmailAppCore() {
  const [searchParams, setSearchParams] = useSearchParams();

  // ----------------------------
  // router params: accounts + mailbox <-> state (loop-safe)
  // ----------------------------
  const accountsParam = searchParams.get("accounts") ?? "";
  const mailboxParam = searchParams.get("mailbox") ?? "";
  const qParam = searchParams.get("q") ?? "";

  const urlAccounts = useMemo(
    () => parseAccountsParam(accountsParam),
    [accountsParam]
  );

  const urlMailbox = useMemo(() => {
    const mb = mailboxParam.trim();
    return mb ? mb : DEFAULT_MAILBOX;
  }, [mailboxParam]);

  const urlQuery = useMemo(() => qParam.trim(), [qParam]);

  // Initialize state from URL once
  const [filterAccounts, setFilterAccounts] = useState<string[]>(
    () => parseAccountsParam(accountsParam)
  );

  const [currentMailbox, setCurrentMailbox] = useState<string>(
    () => (mailboxParam.trim() ? mailboxParam.trim() : DEFAULT_MAILBOX)
  );

  const [searchText, setSearchText] = useState<string>(() => urlQuery);
  const [appliedSearchText, setAppliedSearchText] = useState<string>(() => urlQuery);

  // If state update originated from URL navigation, skip writing it back once
  const syncingFromUrl = useRef(false);

  // URL -> state (e.g. back/forward navigation, link sharing)
  useEffect(() => {
    const nextAccounts = urlAccounts;
    const nextMailbox = urlMailbox;
    const nextQuery = urlQuery;

    const accountsChanged = !sameArray(filterAccounts, nextAccounts);
    const mailboxChanged = currentMailbox !== nextMailbox;
    const queryChanged = appliedSearchText !== nextQuery;

    if (!accountsChanged && !mailboxChanged && !queryChanged) return;

    syncingFromUrl.current = true;
    if (accountsChanged) setFilterAccounts(nextAccounts);
    if (mailboxChanged) setCurrentMailbox(nextMailbox);

    if (queryChanged) {
      setAppliedSearchText(nextQuery);
      setSearchText(nextQuery);
    }

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accountsParam, mailboxParam, qParam]); // intentionally depend on raw strings

  // state -> URL (single writer for both params)
  useEffect(() => {
    if (syncingFromUrl.current) {
      syncingFromUrl.current = false;
      return;
    }

    const encodedAccounts = toAccountsParam(filterAccounts) ?? "";
    const encodedMailbox =
      currentMailbox && currentMailbox !== DEFAULT_MAILBOX
        ? String(currentMailbox).trim()
        : "";

    const encodedQ = appliedSearchText.trim();

    const curAccounts = accountsParam;
    const curMailbox = mailboxParam;
    const curQ = qParam;

    // If nothing changed, no-op
    if (
      encodedAccounts === curAccounts &&
      encodedMailbox === curMailbox &&
      encodedQ === curQ
    )
      return;

    const next = new URLSearchParams(searchParams);

    if (encodedAccounts) next.set("accounts", encodedAccounts);
    else next.delete("accounts");

    if (encodedMailbox) next.set("mailbox", encodedMailbox);
    else next.delete("mailbox");

    if (encodedQ) next.set("q", encodedQ);
    else next.delete("q");

    setSearchParams(next, { replace: true });
  }, [
    filterAccounts,
    currentMailbox,
    appliedSearchText,
    accountsParam,
    qParam,
    mailboxParam,
    searchParams,
    setSearchParams,
  ]);

  // mailbox state
  const [mailboxData, setMailboxData] = useState<MailboxData>({});

  // overview + paging (cursor-based)
  const [emails, setEmails] = useState<EmailOverview[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);

  const pageSize = 50;
  const [totalEmails, setTotalEmails] = useState<number>(0);
  const [isLoadingMore, setIsLoadingMore] = useState(false);

  // selection + detail
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedOverview, setSelectedOverview] = useState<EmailOverview | null>(
    null
  );
  const [selectedMessage, setSelectedMessage] = useState<EmailMessage | null>(
    null
  );

  // errors (inline)
  const [listError, setListError] = useState<string>("");
  const [detailError, setDetailError] = useState<string>("");

  // derived: color map (single source of truth)
  const colorMap = useMemo(
    () => buildColorMap(emails, mailboxData),
    [emails, mailboxData]
  );


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
      const data = await EmailApi.getMailboxes();
      setMailboxData(data || {});
    } catch (e) {
      console.error("Error fetching mailboxes:", e);
      setListError("Failed to fetch mailboxes.");
    }
  }, []);

  const fetchOverview = useCallback(
    async (direction: null | "next" = null) => {
      try {
        setListError("");
        
        if (direction === "next") {
          if (isLoadingMore) return;
          if (!nextCursor) return;
          setIsLoadingMore(true);
        } else {
          // fresh load
          setNextCursor(null);
        }

        const useCursor = direction === "next" ? nextCursor ?? undefined : undefined;        

        const payload = await EmailApi.getOverview({
          mailbox: currentMailbox,
          limit: pageSize,
          search_query: appliedSearchText.trim() ? appliedSearchText.trim() : undefined,
          cursor: useCursor,
          accounts: useCursor
            ? undefined
            : filterAccounts.length
            ? [...filterAccounts]
            : undefined,
        });
        

        const list = Array.isArray(payload.data) ? payload.data : [];
        const meta = payload.meta ?? {};

        if (direction === "next") {
          setEmails((prev) => mergeUniqueById(prev, list));
        } else {
          setEmails(list);
        }

        // reset selection on new list
        setSelectedId(null);
        setSelectedOverview(null);
        setSelectedMessage(null);
        setDetailError("");

        setNextCursor(meta.next_cursor ?? null);

        const total =
          typeof meta.total_count === "number" ? meta.total_count : undefined;
        if (typeof total === "number" && total >= 0) {
          setTotalEmails(total);
        }
      } catch (e) {
        console.error("Error fetching overview:", e);
        if (direction !== "next") setEmails([]);
        setListError("Failed to fetch emails.");
      } finally {
        setIsLoadingMore(false);
      }
    },
    [currentMailbox, pageSize, nextCursor, filterAccounts, appliedSearchText, isLoadingMore]
  );

  const applySearch = useCallback(() => {
    const next = searchText.trim();
    setAppliedSearchText(next);
  }, [searchText]);

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

        const msg = await EmailApi.getEmail({
          account: String(account),
          mailbox: String(mailbox),
          uid: uid,
        });
        console.log(msg.headers);
        

        setSelectedMessage(msg);
      } catch (e) {
        console.error("Error fetching email detail:", e);
        setDetailError("Failed to load full email content.");
        setSelectedMessage(null);
      }
    },
    [currentMailbox]
  );

  useEffect(() => {
    void fetchMailboxes();
  }, [fetchMailboxes]);

  const lastAppliedKey = useRef<string>("");
  useEffect(() => {
    const key = `${currentMailbox}::${toAccountsParam(filterAccounts) ?? ""}::${appliedSearchText}`;
    if (key === lastAppliedKey.current) return;
    lastAppliedKey.current = key;

    void fetchOverview(null);
  }, [currentMailbox, filterAccounts, appliedSearchText, fetchOverview]);

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

  const legendAccounts = useMemo(
    () => Object.keys(mailboxData || {}),
    [mailboxData]
  );

  const helpers = useMemo(() => {
    return {
      getEmailId: (e: EmailOverview) => getEmailId(e),
      findAccountForEmail: (e: EmailOverview) =>
        findAccountForEmail(e, mailboxData),
      getColorForEmail: (e: EmailOverview) =>
        getColorForEmail(e, mailboxData, colorMap),
    };
  }, [mailboxData, colorMap]);

  return {
    mailboxData,
    currentMailbox,
    setCurrentMailbox,

    filterAccounts,
    setFilterAccounts,

    emails,
    nextCursor,
    totalEmails,
    isLoadingMore,

    searchText,
    setSearchText,
    applySearch,

    selectedId,
    selectedOverview,
    selectedMessage,
    getSelectedRef,
    selectEmail,

    listError,
    detailError,
    setDetailError,

    fetchMailboxes,
    fetchOverview,

    legendAccounts,
    legendColorMap: colorMap,

    helpers,
  };
}
