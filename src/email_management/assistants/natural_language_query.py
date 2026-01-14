from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING
from pydantic import BaseModel, Field
from email_management.llm import get_model
from email_management.email_query import EasyIMAPQuery
from email_management.imap import IMAPQuery

if TYPE_CHECKING:
    from email_management.email_manager import EmailManager

class HeaderFilter(BaseModel):
    name: str = Field(
        description="Exact header name to inspect, for example 'List-Unsubscribe' or 'X-Provider'."
    )
    value: str = Field(
        description=(
            "Substring that must appear in the given header's value for the message to match."
        )
    )


class IMAPFlagsPlan(BaseModel):
    """
    Boolean flags describing required or forbidden message states.
    A value of True means the message must have that state.
    """

    seen: bool = Field(
        default=False,
        description="If true, match messages that are marked as read/seen.",
    )
    unseen: bool = Field(
        default=False,
        description="If true, match messages that are not marked as read/seen.",
    )
    answered: bool = Field(
        default=False,
        description="If true, match messages that have been replied to.",
    )
    unanswered: bool = Field(
        default=False,
        description="If true, match messages that have not been replied to.",
    )
    flagged: bool = Field(
        default=False,
        description="If true, match messages that are flagged/starred.",
    )
    unflagged: bool = Field(
        default=False,
        description="If true, match messages that are not flagged/starred.",
    )
    deleted: bool = Field(
        default=False,
        description="If true, match messages that are marked for deletion.",
    )
    undeleted: bool = Field(
        default=False,
        description="If true, match messages that are not marked for deletion.",
    )
    draft: bool = Field(
        default=False,
        description="If true, match messages that are drafts.",
    )
    undraft: bool = Field(
        default=False,
        description="If true, match messages that are not drafts.",
    )
    recent: bool = Field(
        default=False,
        description="If true, match messages that have newly arrived in the mailbox.",
    )
    new: bool = Field(
        default=False,
        description="If true, match messages that are both recently arrived and still unread.",
    )


class IMAPExcludePlan(BaseModel):
    """
    Negative filters: any value here describes content that must NOT be present.
    """

    from_: List[str] = Field(
        default_factory=list,
        description="Messages whose sender matches any of these strings MUST be excluded.",
    )
    to: List[str] = Field(
        default_factory=list,
        description="Messages whose 'To' recipient matches any of these strings MUST be excluded.",
    )
    cc: List[str] = Field(
        default_factory=list,
        description="Messages whose 'Cc' recipient matches any of these strings MUST be excluded.",
    )
    bcc: List[str] = Field(
        default_factory=list,
        description="Messages whose 'Bcc' recipient matches any of these strings MUST be excluded.",
    )
    subject: List[str] = Field(
        default_factory=list,
        description="Messages whose subject contains any of these substrings MUST be excluded.",
    )
    header: List[HeaderFilter] = Field(
        default_factory=list,
        description=(
            "Messages whose given header contains the specified substring MUST be excluded. "
            "Each entry describes a header name and a disallowed value substring."
        ),
    )
    text: List[str] = Field(
        default_factory=list,
        description=(
            "Messages whose headers or body text contain any of these substrings MUST be excluded."
        ),
    )
    body: List[str] = Field(
        default_factory=list,
        description="Messages whose body text contains any of these substrings MUST be excluded.",
    )


class IMAPClauses(BaseModel):
    """
    One AND-clause in Disjunctive Normal Form.

    All fields in a single clause describe conditions that must be true at
    the same time for a message to match that clause.
    """

    from_: List[str] = Field(
        default_factory=list,
        description=(
            "Sender filter: each entry is a substring that must appear in the message's sender "
            "address or display name. All listed values are ANDed together within the clause."
        ),
    )
    to: List[str] = Field(
        default_factory=list,
        description=(
            "Recipient filter (To): each entry is a substring that must appear among the primary "
            "recipients. All listed values are ANDed together within the clause."
        ),
    )
    cc: List[str] = Field(
        default_factory=list,
        description=(
            "Recipient filter (Cc): each entry is a substring that must appear among the Cc "
            "recipients. All listed values are ANDed together within the clause."
        ),
    )
    bcc: List[str] = Field(
        default_factory=list,
        description=(
            "Recipient filter (Bcc): each entry is a substring that must appear among the Bcc "
            "recipients. All listed values are ANDed together within the clause."
        ),
    )
    subject: List[str] = Field(
        default_factory=list,
        description=(
            "Subject filter: each entry is a substring that must appear in the message subject. "
            "All listed values are ANDed together within the clause."
        ),
    )
    text: List[str] = Field(
        default_factory=list,
        description=(
            "Free-text filter: each entry is a substring that must appear somewhere in the "
            "message headers OR body text. All listed values are ANDed together within the clause."
        ),
    )
    body: List[str] = Field(
        default_factory=list,
        description=(
            "Body-only filter: each entry is a substring that must appear in the message body "
            "content. All listed values are ANDed together within the clause."
        ),
    )
    header: List[HeaderFilter] = Field(
        default_factory=list,
        description=(
            "Header-based filters: for each entry, the specified header must contain the given "
            "value substring for the message to match this clause."
        ),
    )

    since: Optional[str] = Field(
        default=None,
        description=(
            "Earliest allowed message date (inclusive). Only messages on or after this date "
            "match this clause. Format: 'YYYY-MM-DD'."
        ),
    )
    before: Optional[str] = Field(
        default=None,
        description=(
            "Upper bound on message date (exclusive). Only messages strictly before this date "
            "match this clause. Format: 'YYYY-MM-DD'."
        ),
    )
    on: Optional[str] = Field(
        default=None,
        description=(
            "Exact message date filter. Only messages whose date equals this day match this clause. "
            "Format: 'YYYY-MM-DD'."
        ),
    )
    sent_since: Optional[str] = Field(
        default=None,
        description=(
            "Earliest allowed sent date (inclusive). Only messages sent on or after this date "
            "match this clause. Format: 'YYYY-MM-DD'."
        ),
    )
    sent_before: Optional[str] = Field(
        default=None,
        description=(
            "Upper bound on sent date (exclusive). Only messages sent before this date match "
            "this clause. Format: 'YYYY-MM-DD'."
        ),
    )
    sent_on: Optional[str] = Field(
        default=None,
        description=(
            "Exact sent date filter. Only messages whose sent date equals this day match this clause. "
            "Format: 'YYYY-MM-DD'."
        ),
    )

    flags: IMAPFlagsPlan = Field(
        default_factory=IMAPFlagsPlan,
        description=(
            "Message state filters (read/unread, replied, flagged, draft, etc.). Only messages "
            "whose flags satisfy all enabled conditions are included in this clause."
        ),
    )

    # size
    larger: Optional[int] = Field(
        default=None,
        description=(
            "Minimum message size in bytes. Only messages strictly larger than this value "
            "match this clause."
        ),
    )
    smaller: Optional[int] = Field(
        default=None,
        description=(
            "Maximum message size in bytes. Only messages strictly smaller than this value "
            "match this clause."
        ),
    )

    keyword: List[str] = Field(
        default_factory=list,
        description=(
            "Required keywords: each entry is a keyword or label that the message must have. "
            "All listed values are ANDed together within the clause."
        ),
    )
    unkeyword: List[str] = Field(
        default_factory=list,
        description=(
            "Forbidden keywords: each entry is a keyword or label that the message must NOT have. "
            "A message is excluded from this clause if it has any of these."
        ),
    )

    uid: List[str] = Field(
        default_factory=list,
        description=(
            "UID-based restriction. Entries are either individual numeric identifiers or ranges "
            "like 'start:end'. Only messages whose UID falls within this set are included."
        ),
    )

    excludes: IMAPExcludePlan = Field(
        default_factory=IMAPExcludePlan,
        description=(
            "Negative content filters for this clause. Any message matching these exclusion "
            "rules is removed from the result even if it matches other conditions."
        ),
    )

    use_newsletters: bool = Field(
        default=False,
        description=(
            "If true, restrict this clause to messages that resemble newsletters or "
            "marketing/announcement mailings, typically subscription-style emails."
        ),
    )

    use_invoices_or_receipts: bool = Field(
        default=False,
        description=(
            "If true, restrict this clause to finance-related transactional emails such as "
            "invoices, receipts, payment confirmations, or order confirmations."
        ),
    )

    use_security_alerts: bool = Field(
        default=False,
        description=(
            "If true, restrict this clause to security or account alerts, such as login "
            "notifications, password changes, or verification-code emails."
        ),
    )

    use_with_attachments_hint: bool = Field(
        default=False,
        description=(
            "If true, restrict this clause to messages that likely include file attachments, "
            "approximated by searching for common attachment-related markers in the content."
        ),
    )

    raw_tokens: List[str] = Field(
        default_factory=list,
        description=(
            "Extra IMAP search tokens that apply only inside this clause. These are appended "
            "directly to the constructed search expression for this clause."
        ),
    )


class IMAPLowLevelPlan(BaseModel):
    """
    A full low-level search plan expressed in Disjunctive Normal Form (DNF).
    """

    clauses: List[IMAPClauses] = Field(
        default_factory=list,
        description=(
            "List of clauses; each clause describes a set of conditions that must all hold for "
            "a message to match, and the overall result is the union of messages matched by any clause."
        ),
    )

    raw_tokens: List[str] = Field(
        default_factory=list,
        description=(
            "Additional IMAP search tokens that are appended to the final query after all clauses "
            "have been combined. These affect the entire search, not just a single clause."
        ),
    )

    notes: Optional[str] = Field(
        default=None,
        description=(
            "Optional free-form explanation of the intended meaning of this plan, useful for "
            "debugging or logging but not used for filtering."
        ),
    )

EMAIL_IMAP_QUERY_PROMPT = """
You are an assistant that translates NATURAL LANGUAGE email-search requests
into a JSON object that matches the Pydantic model `IMAPLowLevelPlan`.

The resulting plan describes email filters in Disjunctive Normal Form (DNF):

- `clauses` is a list of filter clauses.
- The overall meaning is: a message matches if it satisfies ANY one clause
  (clause_1 OR clause_2 OR ...).

Within a single clause:

- All specified conditions in that clause must be satisfied at the same time
  (logical AND within the clause).
- IMPORTANT: For any list field in a clause (e.g. from_, to, cc, bcc, subject,
  text, body, header, keyword, unkeyword, uid, raw_tokens, excludes.*), MULTIPLE
  VALUES ARE INTERPRETED AS LOGICAL AND. That is, every listed value must match
  for that field.
- If the user wants OR semantics between multiple values for the same kind of
  condition (e.g. "from Google OR Microsoft", "subject contains 'invoice' OR
  'receipt'"), you MUST express this using MULTIPLE CLAUSES, one per alternative.
  For example:
    - Clause 1: from_ = ["google.com"]
    - Clause 2: from_ = ["microsoft.com"]
  so that the overall `clauses` acts as OR.

The clause may constrain:
  - sender and recipients (from_, to, cc, bcc)
  - subject and body text (subject, text, body)
  - specific headers (header)
  - dates and sent-dates (since, before, on, sent_since, sent_before, sent_on)
  - message state (flags)
  - message size (larger, smaller)
  - keywords and labels (keyword, unkeyword)
  - UID ranges (uid)
  - explicit exclusions (excludes)
  - and may optionally mark the clause as focusing on newsletters, invoices/receipts,
    security alerts, or messages likely to include attachments.

Interpret the fields as follows:

- from_ / to / cc / bcc:
  Each list entry is a substring used to restrict who sent or received the email.
  Within a clause, all listed values for a field are required (logical AND).

- subject:
  Each list entry is a substring that must appear in the subject. All listed
  values are required when present (logical AND).

- text:
  Each list entry is a substring that must appear somewhere in the headers OR
  body of the message. All listed values are required (logical AND).

- body:
  Each list entry is a substring that must appear in the message body only.
  All listed values are required (logical AND).

- header:
  Each entry describes a header name and a required substring in that header's value.
  All header conditions within a clause must be satisfied (logical AND).

- since / before / on:
  Date constraints based on the message date. Use ISO strings 'YYYY-MM-DD'.

- sent_since / sent_before / sent_on:
  Date constraints based on the message's sent date. Use ISO strings 'YYYY-MM-DD'.

- flags:
  A set of boolean filters describing whether the message should be read/unread,
  answered/unanswered, flagged/unflagged, draft/undraft, recent/new, etc.

- larger / smaller:
  Minimum and maximum message sizes in bytes (strict inequalities).

- keyword:
  Required keywords or labels; every listed keyword must be present (logical AND).

- unkeyword:
  Forbidden keywords or labels; messages are excluded if they have any of these.

- uid:
  Restrictions based on message UID, using individual identifiers or ranges such
  as '100:200'. All listed UID restrictions are combined with AND unless encoded
  as separate clauses.

- excludes:
  Negative filters; any message whose sender/recipient/subject/header/text/body
  matches these exclusion rules is removed from the result, even if it matched
  the positive filters. Multiple values in the same excludes list are combined
  with AND (the message must match all those exclusion conditions to be removed).

- use_newsletters:
  If true, the clause is intended to match emails that look like newsletters or
  subscription-style marketing/announcement mail.

- use_invoices_or_receipts:
  If true, the clause is intended to match finance-related transactional emails
  such as invoices, receipts, payment confirmations, or order confirmations.

- use_security_alerts:
  If true, the clause is intended to match security or account alerts, including
  login notifications, password-change messages, and verification-code emails.

- use_with_attachments_hint:
  If true, the clause is intended to emphasize emails that likely contain file
  attachments, approximated by searching for attachment-related markers.

- raw_tokens (at the clause level):
  Extra raw IMAP search tokens that apply only to that clause. Multiple tokens
  in this list are combined with AND semantics.

At the top level:

- raw_tokens:
  Extra IMAP search tokens that apply to the entire search, after all clauses.
  Multiple tokens here are also combined with AND semantics.

Your task:

1. Read the user's natural-language request describing which emails they want.
2. Construct one or more clauses, using the fields above, so that the overall
   result matches the described intent.
3. Remember: multiple values in the SAME LIST FIELD inside a clause are ANDed.
   If the user speaks about alternatives with OR semantics (e.g. "A or B"), you
   should create separate clauses (one per alternative), so they are combined
   with OR at the top-level `clauses`.
4. Use several clauses if the user describes different categories of emails that
   should be combined with OR semantics (e.g. "either invoices OR security alerts").
5. When date or state information is unclear or not requested, simply leave those
   fields at their default values or omit them.

Constraints:

- You MUST output a single JSON object that can be parsed as `IMAPLowLevelPlan`.
- Do NOT output Python code, comments, or explanations.
- Do NOT invent fields that are not defined in the Pydantic models.
- Prefer clear, minimal conditions that directly capture the user's request.

User request:
{user_request}
"""


def _apply_imap_clauses(q: IMAPQuery, c: IMAPClauses) -> None:
    """
    Apply the low-level IMAPQuery part of one clause to an IMAPQuery instance.
    """

    # basic positive fields
    for s in c.from_:
        q.from_(s)
    for s in c.to:
        q.to(s)
    for s in c.cc:
        q.cc(s)
    for s in c.bcc:
        q.bcc(s)
    for s in c.subject:
        q.subject(s)
    for s in c.text:
        q.text(s)
    for s in c.body:
        q.body(s)
    for hf in c.header:
        if hf.name and hf.value:
            q.header(hf.name, hf.value)

    # dates
    if c.since:
        q.since(c.since)
    if c.before:
        q.before(c.before)
    if c.on:
        q.on(c.on)
    if c.sent_since:
        q.sent_since(c.sent_since)
    if c.sent_before:
        q.sent_before(c.sent_before)
    if c.sent_on:
        q.sent_on(c.sent_on)

    # flags
    f = c.flags
    if f.seen:
        q.seen()
    if f.unseen:
        q.unseen()
    if f.answered:
        q.answered()
    if f.unanswered:
        q.unanswered()
    if f.flagged:
        q.flagged()
    if f.unflagged:
        q.unflagged()
    if f.deleted:
        q.deleted()
    if f.undeleted:
        q.undeleted()
    if f.draft:
        q.draft()
    if f.undraft:
        q.undraft()
    if f.recent:
        q.recent()
    if f.new:
        q.new()

    # size
    if c.larger is not None:
        q.larger(c.larger)
    if c.smaller is not None:
        q.smaller(c.smaller)

    # keyword / unkeyword
    for kw in c.keyword:
        q.keyword(kw)
    for kw in c.unkeyword:
        q.unkeyword(kw)

    # uid
    if c.uid:
        q.uid(*c.uid)

    # excludes
    ex = c.excludes
    for s in ex.from_:
        q.exclude_from(s)
    for s in ex.to:
        q.exclude_to(s)
    for s in ex.cc:
        q.exclude_cc(s)
    for s in ex.bcc:
        q.exclude_bcc(s)
    for s in ex.subject:
        q.exclude_subject(s)
    for hf in ex.header:
        if hf.name and hf.value:
            q.exclude_header(hf.name, hf.value)
    for s in ex.text:
        q.exclude_text(s)
    for s in ex.body:
        q.exclude_body(s)

    # clause-local raw tokens
    if c.raw_tokens:
        q.raw(*c.raw_tokens)


def _apply_clause_to_easy(easy: EasyIMAPQuery, c: IMAPClauses) -> None:
    """
    Apply ONE clause to an EasyIMAPQuery:
    - First, clause-local high-level filters (newsletters, invoices/receipts, security alerts,
      with-attachments hint).
    - Then, low-level IMAPQuery primitives onto easy.query.
    """

    if c.use_newsletters:
        easy.newsletters()

    if c.use_invoices_or_receipts:
        easy.invoices_or_receipts()

    if c.use_security_alerts:
        easy.security_alerts()

    if c.use_with_attachments_hint:
        easy.with_attachments_hint()

    _apply_imap_clauses(easy.query, c)


def _apply_low_level_to_easy_query(easy: EasyIMAPQuery, low: IMAPLowLevelPlan) -> None:
    """
    Apply IMAPLowLevelPlan (DNF) onto an EasyIMAPQuery.

    - If 0 clauses: do nothing.
    - If 1 clause: AND it directly into `easy` (helpers + low-level).
    - If N>=2 clauses:
        * Build N sub-queries with separate EasyIMAPQuery instances.
        * Combine them with OR into the main easy.query via easy.query.or_(*subqueries).
    """

    if not low.clauses:
        pass
    elif len(low.clauses) == 1:
        _apply_clause_to_easy(easy, low.clauses[0])
    else:
        subqueries: List[IMAPQuery] = []

        for clause in low.clauses:
            sub_q = IMAPQuery()

            clause_easy = EasyIMAPQuery(None, "INBOX")
            clause_easy.query = sub_q

            _apply_clause_to_easy(clause_easy, clause)
            subqueries.append(sub_q)

        easy.query.or_(*subqueries)

    if low.raw_tokens:
        easy.raw(*low.raw_tokens)


def llm_easy_imap_query_from_nl(
    user_request: str,
    *,
    provider: str,
    model_name: str,
    manager: Optional[EmailManager],
    mailbox: str = "INBOX",
) -> Tuple[EasyIMAPQuery, Dict[str, Any]]:
    """
    Use an LLM to translate a natural-language request into an EasyIMAPQuery,
    where the final LLM output schema is IMAPLowLevelPlan (a list of DNF clauses).
    """
    chain = get_model(provider, model_name, IMAPLowLevelPlan)
    result, llm_call_info = chain(
        EMAIL_IMAP_QUERY_PROMPT.format(user_request=user_request)
    )
    plan = result

    easy = manager.imap_query(mailbox)
    _apply_low_level_to_easy_query(easy, plan)

    return easy, llm_call_info

