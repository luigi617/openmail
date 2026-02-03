from __future__ import annotations

from typing import List, Optional

from openmail.imap import IMAPClient, IMAPQuery
from openmail.models import UnsubscribeCandidate
from openmail.subscription.parser import parse_list_unsubscribe


class SubscriptionDetector:
    def __init__(self, imap: IMAPClient):
        self.imap = imap

    def find(
        self,
        *,
        mailbox: str = "INBOX",
        limit: int = 200,
        since: Optional[str] = None,
        unseen_only: bool = False,
    ) -> List[UnsubscribeCandidate]:
        q = IMAPQuery()
        if unseen_only:
            q.unseen()
        if since:
            q.since(since)

        page = self.imap.search_page_cached(mailbox=mailbox, query=q, page_size=limit)
        msgs = self.imap.fetch(page.refs)

        out: List[UnsubscribeCandidate] = []
        for ref, msg in zip(page.refs, msgs):
            headers = msg.headers
            lu = _get_header(headers, "List-Unsubscribe")
            if not lu:
                continue

            methods = parse_list_unsubscribe(lu)
            if not methods:
                continue

            out.append(
                UnsubscribeCandidate(
                    ref=ref,
                    from_email=msg.from_email,
                    subject=msg.subject,
                    methods=methods,
                )
            )
        return out


def _get_header(headers: dict, name: str) -> str:
    name = name.lower()
    for k, v in headers.items():
        if k.lower() == name:
            return v
    return ""
