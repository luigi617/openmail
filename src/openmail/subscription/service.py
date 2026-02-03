from email.message import EmailMessage as PyEmailMessage
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from openmail.models import (
    UnsubscribeActionResult,
    UnsubscribeCandidate,
    UnsubscribeMethod,
)
from openmail.smtp import SMTPClient
from openmail.types import SendResult


def _http_unsubscribe_flow(url: str, timeout: int = 10) -> tuple[bool, str]:
    """
    Best-effort HTTP unsubscribe:

    1. GET the URL
    2. If HTML, try to:
       - find and submit an 'unsubscribe' / 'opt out' form
       - otherwise, follow an 'unsubscribe' / 'opt out' link/button
    3. Fall back to treating the initial GET as the unsubscribe action.
    """
    session = requests.Session()

    r = session.get(url, timeout=timeout, allow_redirects=True)
    status = r.status_code

    content_type = r.headers.get("Content-Type", "")
    if "html" not in content_type.lower():
        ok = 200 <= status < 300
        return ok, f"GET {r.url} -> HTTP {status} (non-HTML content)"

    soup = BeautifulSoup(r.text, "html.parser")

    def _is_unsub_text(s: str) -> bool:
        s = s.lower()
        return (
            "unsubscribe" in s
            or "opt out" in s
            or "opt-out" in s
            or "optout" in s
        )

    unsub_form = None
    for form in soup.find_all("form"):
        text_parts = [
            form.get("id", ""),
            form.get("name", ""),
            form.get("action", ""),
            form.get_text(" ", strip=True),
        ]
        combined = " ".join(text_parts)
        if _is_unsub_text(combined):
            unsub_form = form
            break

    if unsub_form is not None:
        action_attr = unsub_form.get("action") or ""
        action_url = urljoin(r.url, action_attr) if action_attr else r.url
        method = (unsub_form.get("method") or "post").lower()

        data: dict[str, str] = {}
        for inp in unsub_form.find_all("input"):
            name = inp.get("name")
            if not name:
                continue

            itype = (inp.get("type") or "text").lower()
            value = inp.get("value", "")

            if itype in ("checkbox", "radio"):
                # Only send checked ones
                if inp.has_attr("checked"):
                    data[name] = value or "on"
            else:
                data[name] = value

        for sel in unsub_form.find_all("select"):
            name = sel.get("name")
            if not name:
                continue
            selected = sel.find("option", selected=True) or sel.find("option")
            if selected and selected.get("value") is not None:
                data[name] = selected.get("value")

        if method == "post":
            r2 = session.post(action_url, data=data, timeout=timeout)
        else:
            r2 = session.get(action_url, params=data, timeout=timeout)

        soup2 = BeautifulSoup(r2.text, "html.parser")
        text = soup2.get_text(" ", strip=True)
        text = " ".join(text.split())

        ok = 200 <= r2.status_code < 300
        detail = (
            f"{method.upper()} {action_url} -> HTTP {r2.status_code} "
            f"(submitted unsubscribe form). "
            f"Final confirmation page body: \n {text[:2000]}"
        )
        return ok, detail

    unsub_link = None
    for tag in soup.find_all(["a", "button"]):
        text = (tag.get_text(" ", strip=True) or "")
        if _is_unsub_text(text):
            unsub_link = tag
            break

    if unsub_link is not None and unsub_link.name == "a":
        href = unsub_link.get("href")
        if href:
            click_url = urljoin(r.url, href)
            r2 = session.get(click_url, timeout=timeout, allow_redirects=True)
            ok = 200 <= r2.status_code < 300
            detail = f"GET {click_url} -> HTTP {r2.status_code} (clicked unsubscribe link)"
            return ok, detail

    ok = 200 <= status < 300
    return ok, f"GET {r.url} -> HTTP {status} (no explicit form/link found)"


class SubscriptionService:
    def __init__(self, smtp: SMTPClient):
        self.smtp = smtp

    def unsubscribe(
        self,
        candidates: List[UnsubscribeCandidate],
        *,
        prefer: str = "mailto",
        from_addr: Optional[str] = None,
    ) -> Dict[str, List[UnsubscribeActionResult]]:
        """
        Executes unsubscribe actions.

        Behavior:
        - mailto: Sends an email to the unsubscribe address.
        - http: Performs an HTTP GET request to the unsubscribe URL.
        """
        results: Dict[str, List[UnsubscribeActionResult]] = {
            "sent": [],
            "http": [],
            "skipped": [],
        }

        for cand in candidates:
            method = _choose_method(cand.methods, prefer)
            if not method:
                results["skipped"].append(
                    UnsubscribeActionResult(
                        ref=cand.ref,
                        method=None,
                        sent=False,
                        note="No supported unsubscribe method",
                    )
                )
                continue

            if method.kind == "mailto":
                msg = PyEmailMessage()
                msg["To"] = method.value
                msg["Subject"] = "Unsubscribe"
                if from_addr:
                    msg["From"] = from_addr
                msg.set_content("Please unsubscribe me.")

                try:
                    send_res = self.smtp.send(msg, [method.value])
                except Exception as exc:
                    send_res = SendResult(ok=False, detail=f"error: {exc!r}")


                results["sent"].append(
                    UnsubscribeActionResult(
                        ref=cand.ref,
                        method=method,
                        sent=True,
                        send_result=send_res,
                    )
                )

            elif method.kind == "http":
                url = method.value
                try:
                    ok, detail = _http_unsubscribe_flow(url)
                    send_result = SendResult(
                        ok=ok,
                        detail=detail,
                    )
                    results["http"].append(
                        UnsubscribeActionResult(
                            ref=cand.ref,
                            method=method,
                            sent=ok,
                            send_result=send_result,
                        )
                    )
                except Exception as e:
                    results["http"].append(
                        UnsubscribeActionResult(
                            ref=cand.ref,
                            method=method,
                            sent=False,
                            send_result=SendResult(ok=False, detail=str(e)),
                            note="HTTP request failed",
                        )
                    )

            else:
                results["skipped"].append(
                    UnsubscribeActionResult(
                        ref=cand.ref,
                        method=method,
                        sent=False,
                        note=f"Unsupported method kind: {method.kind}",
                    )
                )

        return results


def _choose_method(methods: List[UnsubscribeMethod], prefer: str) -> Optional[UnsubscribeMethod]:
    prefer = prefer.lower()
    if prefer == "mailto":
        for m in methods:
            if m.kind == "mailto":
                return m
        for m in methods:
            if m.kind == "http":
                return m
    elif prefer == "http":
        for m in methods:
            if m.kind == "http":
                return m
        for m in methods:
            if m.kind == "mailto":
                return m
    return methods[0] if methods else None
