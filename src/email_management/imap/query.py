from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List


def _imap_date(iso_yyyy_mm_dd: str) -> str:
    dt = datetime.strptime(iso_yyyy_mm_dd, "%Y-%m-%d")
    return dt.strftime("%d-%b-%Y")


def _q(s: str) -> str:
    """
    Quote/escape a string for IMAP SEARCH.
    IMAP uses double quotes for string literals; backslash can escape quotes.
    """
    s = s.replace("\\", "\\\\").replace('"', r"\"")
    return f'"{s}"'

@dataclass
class IMAPQuery:
    parts: List[str] = field(default_factory=list)
    
    # --- basic fields ---
    def from_(self, s: str) -> IMAPQuery:
        self.parts += ["FROM", _q(s)]
        return self

    def to(self, s: str) -> IMAPQuery:
        self.parts += ["TO", _q(s)]
        return self

    def cc(self, s: str) -> IMAPQuery:
        self.parts += ["CC", _q(s)]
        return self

    def bcc(self, s: str) -> IMAPQuery:
        self.parts += ["BCC", _q(s)]
        return self

    def subject(self, s: str) -> IMAPQuery:
        self.parts += ["SUBJECT", _q(s)]
        return self

    def text(self, s: str) -> IMAPQuery:
        """
        Match in headers OR body text.
        """
        self.parts += ["TEXT", _q(s)]
        return self

    def body(self, s: str) -> IMAPQuery:
        """
        Match only in body text.
        """
        self.parts += ["BODY", _q(s)]
        return self
    
    def header(self, name: str, value: str) -> IMAPQuery:
        self.parts += ["HEADER", _q(name), _q(value)]
        return self

    # --- date filters ---
    def since(self, iso_date: str) -> IMAPQuery:
        self.parts += ["SINCE", _imap_date(iso_date)]
        return self

    def before(self, iso_date: str) -> IMAPQuery:
        self.parts += ["BEFORE", _imap_date(iso_date)]
        return self

    def on(self, iso_date: str) -> IMAPQuery:
        self.parts += ["ON", _imap_date(iso_date)]
        return self
    
    def sent_since(self, iso_date: str) -> IMAPQuery:
        self.parts += ["SENTSINCE", _imap_date(iso_date)]
        return self
    
    def sent_before(self, iso_date: str) -> IMAPQuery:
        self.parts += ["SENTBEFORE", _imap_date(iso_date)]
        return self
    
    def sent_on(self, iso_date: str) -> IMAPQuery:
        self.parts += ["SENTON", _imap_date(iso_date)]
        return self

    # --- flags/status ---
    def seen(self) -> IMAPQuery:
        self.parts += ["SEEN"]
        return self

    def unseen(self) -> IMAPQuery:
        self.parts += ["UNSEEN"]
        return self

    def answered(self) -> IMAPQuery:
        self.parts += ["ANSWERED"]
        return self
    
    def unanswered(self) -> IMAPQuery:
        self.parts += ["UNANSWERED"]
        return self

    def flagged(self) -> IMAPQuery:
        self.parts += ["FLAGGED"]
        return self
    
    def unflagged(self) -> IMAPQuery:
        self.parts += ["UNFLAGGED"]
        return self
    
    def deleted(self) -> IMAPQuery:
        self.parts += ["DELETED"]
        return self

    def undeleted(self) -> IMAPQuery:
        self.parts += ["UNDELETED"]
        return self

    def draft(self) -> IMAPQuery:
        self.parts += ["DRAFT"]
        return self

    def undraft(self) -> IMAPQuery:
        self.parts += ["UNDRAFT"]
        return self

    def recent(self) -> IMAPQuery:
        self.parts += ["RECENT"]
        return self

    def new(self) -> IMAPQuery:
        self.parts += ["NEW"]
        return self

    # --- size ---
    def larger(self, n_bytes: int) -> IMAPQuery:
        self.parts += ["LARGER", str(n_bytes)]
        return self

    def smaller(self, n_bytes: int) -> IMAPQuery:
        self.parts += ["SMALLER", str(n_bytes)]
        return self
    
    # --- keyword ---
    def keyword(self, name: str) -> IMAPQuery:
        self.parts += ["KEYWORD", _q(name)]
        return self

    def unkeyword(self, name: str) -> IMAPQuery:
        self.parts += ["UNKEYWORD", _q(name)]
        return self
    
    # --- UID search ---
    def uid(self, *uids: int | str) -> IMAPQuery:
        """
        Accepts ranges ("1:100") or explicit UIDs (1,2,3)
        """
        joined = ",".join(str(u) for u in uids)
        self.parts += ["UID", joined]
        return self

    # --- exclude fields ---
    def _not(self, *tokens: str) -> IMAPQuery:
        """
        Negate a search key: NOT <tokens...>
        """
        self.parts += ["NOT", *tokens]
        return self
    
    def exclude_from(self, s: str) -> IMAPQuery:
        return self._not("FROM", _q(s))

    def exclude_to(self, s: str) -> IMAPQuery:
        return self._not("TO", _q(s))

    def exclude_cc(self, s: str) -> IMAPQuery:
        return self._not("CC", _q(s))

    def exclude_bcc(self, s: str) -> IMAPQuery:
        return self._not("BCC", _q(s))

    def exclude_subject(self, s: str) -> IMAPQuery:
        return self._not("SUBJECT", _q(s))
    
    def exclude_header(self, name: str, value: str) -> IMAPQuery:
        return self._not("HEADER", _q(name), _q(value))

    def exclude_text(self, s: str) -> IMAPQuery:
        return self._not("TEXT", _q(s))

    def exclude_body(self, s: str) -> IMAPQuery:
        return self._not("BODY", _q(s))

    
    def or_(self, *queries: IMAPQuery) -> IMAPQuery:
        """
        Combine multiple IMAPQuery objects using nested OR.
        Example:
            OR(q1, q2, q3) =>
            OR q1 (OR q2 q3)
        """
        if len(queries) < 2:
            raise ValueError("or_many requires at least two queries")

        def fold(qs: List[IMAPQuery]) -> str:
            if len(qs) == 2:
                return f"OR {qs[0].build()} {qs[1].build()}"
            return f"OR {qs[0].build()} {fold(qs[1:])}"

        self.parts.append(fold(list(queries)))
        return self
    
    # --- composition helpers ---
    def all(self) -> IMAPQuery:
        self.parts += ["ALL"]
        return self
    
    def raw(self, *tokens: str) -> IMAPQuery:
        """
        Append raw tokens for advanced users, e.g. raw("OR", 'FROM "a"', 'FROM "b"')
        """
        self.parts += list(tokens)
        return self

    def build(self) -> str:
        return " ".join(self.parts) if self.parts else "ALL"
