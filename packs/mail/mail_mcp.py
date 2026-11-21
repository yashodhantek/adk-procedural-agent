"""Mail MCP server: send a Markdown message as an HTML email.

Providers (MAIL_PROVIDER = auto | graph | smtp):
  graph  Microsoft 365 via the Graph sendMail API, app-only (client credentials).
         MS_TENANT_ID, MS_CLIENT_ID, MS_CLIENT_SECRET, MAIL_FROM (the sending mailbox).
         The app registration needs the Mail.Send *application* permission, the same
         setup the Signal (techintel) platform uses, so its values can be reused.
  smtp   SMTP_HOST, SMTP_PORT (587, STARTTLS), SMTP_USER, SMTP_PASSWORD, MAIL_FROM.
  auto   graph if its variables are set, otherwise smtp.

MAIL_DRY_RUN=1 writes the message to MAIL_OUTBOX_DIR (default ./.data/outbox) instead
of sending, which is useful for testing a schedule.

Run: python packs/mail/mail_mcp.py        (stdio; normally started by the agent)
"""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

import httpx

try:  # mcp >= 2
  from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
  from mcp.server.fastmcp import FastMCP as _Server  # type: ignore

mcp = _Server(name="mail", instructions="Send email. Every call sends a real message unless MAIL_DRY_RUN=1.")

_EMAIL = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")


def recipients(value: str) -> list[str]:
  out = [a.strip() for a in re.split(r"[,;]", value or "") if a.strip()]
  bad = [a for a in out if not _EMAIL.match(a)]
  if bad or not out:
    raise ValueError(f"Invalid recipient list: {value!r}")
  return out


def to_html(markdown_text: str, title: str) -> str:
  try:
    import markdown as md
    body = md.markdown(markdown_text, extensions=["tables", "sane_lists"])
  except ImportError:  # minimal fallback: keep the text readable
    body = f"<pre style='white-space:pre-wrap;font-family:inherit'>{html.escape(markdown_text)}</pre>"
  return f"""<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;font-size:14px;line-height:1.5;color:#1f2328;max-width:760px}}
table{{border-collapse:collapse;margin:8px 0}} th,td{{border:1px solid #d0d7de;padding:4px 8px;text-align:left}}
th{{background:#f6f8fa}} h1{{font-size:20px}} h2{{font-size:16px;margin-top:20px}} blockquote{{color:#57606a;border-left:3px solid #d0d7de;margin:0;padding-left:10px}}
</style></head><body>{body}</body></html>"""


def _provider() -> str:
  p = (os.environ.get("MAIL_PROVIDER") or "auto").lower()
  if p == "auto":
    return "graph" if all(os.environ.get(k) for k in ("MS_TENANT_ID", "MS_CLIENT_ID", "MS_CLIENT_SECRET")) else "smtp"
  return p


async def _send_graph(sender: str, to: list[str], cc: list[str], subject: str, html_body: str) -> dict:
  login = (os.environ.get("MS_LOGIN_ENDPOINT") or "https://login.microsoftonline.com").rstrip("/")
  graph = (os.environ.get("MS_GRAPH_ENDPOINT") or "https://graph.microsoft.com").rstrip("/")
  async with httpx.AsyncClient(timeout=30) as client:
    tok = await client.post(f"{login}/{os.environ['MS_TENANT_ID']}/oauth2/v2.0/token", data={
        "grant_type": "client_credentials", "client_id": os.environ["MS_CLIENT_ID"],
        "client_secret": os.environ["MS_CLIENT_SECRET"], "scope": "https://graph.microsoft.com/.default"})
    if tok.status_code != 200:
      raise RuntimeError(f"Microsoft sign-in failed ({tok.status_code}): {tok.text[:300]}")
    message = {"message": {
        "subject": subject, "body": {"contentType": "HTML", "content": html_body},
        "toRecipients": [{"emailAddress": {"address": a}} for a in to],
        "ccRecipients": [{"emailAddress": {"address": a}} for a in cc]}, "saveToSentItems": True}
    r = await client.post(f"{graph}/v1.0/users/{sender}/sendMail", json=message,
                          headers={"Authorization": f"Bearer {tok.json()['access_token']}"})
    if r.status_code != 202:
      raise RuntimeError(f"Graph sendMail failed ({r.status_code}): {r.text[:300]}")
  return {"provider": "graph"}


def _send_smtp(sender: str, to: list[str], cc: list[str], subject: str, text: str, html_body: str) -> dict:
  msg = EmailMessage()
  msg["From"], msg["To"], msg["Subject"] = sender, ", ".join(to), subject
  if cc:
    msg["Cc"] = ", ".join(cc)
  msg.set_content(text)
  msg.add_alternative(html_body, subtype="html")
  host, port = os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT") or 587)
  with smtplib.SMTP(host, port, timeout=30) as s:
    s.starttls(context=ssl.create_default_context())
    if os.environ.get("SMTP_USER"):
      s.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD") or os.environ.get("SMTP_PASS", ""))
    s.send_message(msg)
  return {"provider": "smtp"}


@mcp.tool(description="WRITE: send an email. `markdown` is converted to HTML. `to`/`cc` are comma-separated addresses.")
async def send_email(to: str, subject: str, markdown: str, cc: str = "") -> dict:
  to_list, cc_list = recipients(to), (recipients(cc) if cc else [])
  sender = os.environ.get("MAIL_FROM") or os.environ.get("SMTP_FROM") or ""
  html_body = to_html(markdown, subject)
  if (os.environ.get("MAIL_DRY_RUN") or "").lower() in ("1", "true", "yes"):
    out = Path(os.environ.get("MAIL_OUTBOX_DIR") or ".data/outbox")
    out.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = out / f"{stamp}-{re.sub(r'[^a-z0-9]+', '-', subject.lower()).strip('-')[:40]}.html"
    path.write_text(html_body, encoding="utf-8")
    (path.with_suffix(".json")).write_text(json.dumps({"from": sender, "to": to_list, "cc": cc_list, "subject": subject}))
    return {"sent": False, "dry_run": True, "saved": str(path), "to": to_list}
  if not sender:
    raise ValueError("Set MAIL_FROM (the sending mailbox)")
  provider = _provider()
  if provider == "graph":
    info = await _send_graph(sender, to_list, cc_list, subject, html_body)
  else:
    info = _send_smtp(sender, to_list, cc_list, subject, markdown, html_body)
  return {"sent": True, "to": to_list, "cc": cc_list, "subject": subject, **info}


if __name__ == "__main__":
  mcp.run("stdio")
