import pytest
from email_management.imap.query import IMAPQuery, _imap_date, _q

def test_imap_date_formats_correctly():
    assert _imap_date("2025-01-02") == "02-Jan-2025"
    assert _imap_date("1999-12-31") == "31-Dec-1999"


def test_q_quotes_and_escapes():
    assert _q("hello") == '"hello"'
    assert _q('he"llo') == '"he\\\"llo"'
    assert _q(r"c:\path\to\file") == '"c:\\\\path\\\\to\\\\file"'


def test_from_to_cc_bcc_subject_text_body():
    q = (
        IMAPQuery()
        .from_("from@example.com")
        .to("to@example.com")
        .cc("cc@example.com")
        .bcc("bcc@example.com")
        .subject("Hello")
        .text("foo")
        .body("bar")
    )
    assert q.build() == (
        'FROM "from@example.com" '
        'TO "to@example.com" '
        'CC "cc@example.com" '
        'BCC "bcc@example.com" '
        'SUBJECT "Hello" '
        'TEXT "foo" '
        'BODY "bar"'
    )


def test_header():
    q = IMAPQuery().header("List-Id", "mylist@example.com")
    assert q.build() == 'HEADER "List-Id" "mylist@example.com"'


def test_date_filters():
    q = (
        IMAPQuery()
        .since("2025-01-02")
        .before("2025-01-10")
        .on("2025-01-05")
        .sent_since("2025-01-03")
        .sent_before("2025-01-09")
        .sent_on("2025-01-06")
    )
    
    parts = q.build().split()

    assert "SINCE" in parts
    assert "02-Jan-2025" in parts
    assert "BEFORE" in parts
    assert "10-Jan-2025" in parts
    assert "ON" in parts
    assert "05-Jan-2025" in parts
    assert "SENTSINCE" in parts
    assert "03-Jan-2025" in parts
    assert "SENTBEFORE" in parts
    assert "09-Jan-2025" in parts
    assert "SENTON" in parts
    assert "06-Jan-2025" in parts


def test_flag_status_filters():
    q = (
        IMAPQuery()
        .seen()
        .unseen()
        .answered()
        .unanswered()
        .flagged()
        .unflagged()
        .deleted()
        .undeleted()
        .draft()
        .undraft()
        .recent()
        .new()
    )
    tokens = q.build().split()

    for expected in [
        "SEEN",
        "UNSEEN",
        "ANSWERED",
        "UNANSWERED",
        "FLAGGED",
        "UNFLAGGED",
        "DELETED",
        "UNDELETED",
        "DRAFT",
        "UNDRAFT",
        "RECENT",
        "NEW",
    ]:
        assert expected in tokens


def test_size_filters():
    q = IMAPQuery().larger(1024).smaller(2048)
    assert q.build() == "LARGER 1024 SMALLER 2048"


def test_keyword_and_unkeyword():
    q = IMAPQuery().keyword("mytag").unkeyword("othertag")
    assert q.build() == 'KEYWORD "mytag" UNKEYWORD "othertag"'


def test_uid_single_and_multiple():
    q1 = IMAPQuery().uid(1)
    assert q1.build() == "UID 1"

    q2 = IMAPQuery().uid(1, 2, 3)
    assert q2.build() == "UID 1,2,3"

    q3 = IMAPQuery().uid("1:5", 10)
    assert q3.build() == "UID 1:5,10"


def test_exclude_from_to_cc_bcc_subject():
    q = (
        IMAPQuery()
        .exclude_from("from@example.com")
        .exclude_to("to@example.com")
        .exclude_cc("cc@example.com")
        .exclude_bcc("bcc@example.com")
        .exclude_subject("Spam")
    )
    assert q.build() == (
        'NOT FROM "from@example.com" '
        'NOT TO "to@example.com" '
        'NOT CC "cc@example.com" '
        'NOT BCC "bcc@example.com" '
        'NOT SUBJECT "Spam"'
    )


def test_exclude_header_text_body():
    q = (
        IMAPQuery()
        .exclude_header("List-Id", "mylist@example.com")
        .exclude_text("foo")
        .exclude_body("bar")
    )
    assert q.build() == (
        'NOT HEADER "List-Id" "mylist@example.com" '
        'NOT TEXT "foo" '
        'NOT BODY "bar"'
    )


def test_or_combines_queries_with_nested_or():
    q1 = IMAPQuery().from_("a@example.com")
    q2 = IMAPQuery().to("b@example.com")
    q3 = IMAPQuery().subject("hello")

    combined = IMAPQuery().or_(q1, q2, q3)
    
    assert combined.build() == (
        'OR FROM "a@example.com" OR TO "b@example.com" SUBJECT "hello"'
    )


def test_or_requires_at_least_two_queries():
    q = IMAPQuery()
    one = IMAPQuery().from_("a@example.com")

    with pytest.raises(ValueError):
        q.or_(one)


def test_raw_appends_tokens():
    q = IMAPQuery().raw("UNSEEN", "FROM", _q("x@example.com"))
    assert q.build() == 'UNSEEN FROM "x@example.com"'


def test_all_on_empty_query_and_default_build():
    
    q_empty = IMAPQuery()
    assert q_empty.build() == "ALL"

    
    q = IMAPQuery().all()
    assert q.build() == "ALL"


def test_chaining_builds_expected_query():
    q = (
        IMAPQuery()
        .from_("a@example.com")
        .to("b@example.com")
        .unseen()
        .since("2025-01-01")
        .smaller(5000)
    )
    assert q.build() == (
        'FROM "a@example.com" '
        'TO "b@example.com" '
        "UNSEEN "
        "SINCE 01-Jan-2025 "
        "SMALLER 5000"
    )
