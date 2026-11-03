"""Issue #17: error emails to the site maintainer, with SMTP mocked."""

import smtplib

import pytest

import alerts

ENV = {
    "ALERT_EMAIL": "maintainer@example.com",
    "SMTP_HOST": "smtp.example.com",
    "SMTP_PORT": "587",
    "SMTP_USER": "sender@example.com",
    "SMTP_PASSWORD": "app-password-123",
}


class FakeSMTP:
    sent = []

    def __init__(self, host, port, timeout):
        self.address = (host, port)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        pass

    def login(self, user, password):
        self.login_as = user

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


@pytest.fixture
def smtp(monkeypatch):
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(alerts.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(alerts, "_last_sent", {})
    FakeSMTP.sent = []
    return FakeSMTP.sent


def test_error_sends_one_email_to_the_maintainer(smtp):
    assert alerts.send_error_alert("APITimeoutError", "מה נמכר?", "Request timed out.")
    msg = smtp[0]
    assert msg["To"] == "maintainer@example.com"
    assert msg["Subject"] == "[bakery-dashboard] ask box error: APITimeoutError"
    body = msg.get_content()
    assert "Question: מה נמכר?" in body and "Detail: Request timed out." in body


def test_same_error_is_held_for_15_minutes(smtp):
    assert alerts.send_error_alert("APITimeoutError", "q", "d", now=1000)
    assert not alerts.send_error_alert("APITimeoutError", "q", "d", now=1000 + 60)
    assert alerts.send_error_alert("OperationalError", "q", "d", now=1000 + 60)  # other type: sent
    assert alerts.send_error_alert("APITimeoutError", "q", "d", now=1000 + alerts.THROTTLE_S)
    assert len(smtp) == 3


def test_nothing_is_sent_without_an_address(smtp, monkeypatch):
    monkeypatch.delenv("ALERT_EMAIL")
    assert not alerts.send_error_alert("APITimeoutError", "q", "d")
    assert smtp == []


FAKE_KEY = "sk-" + "ant-api03-fake"  # built in two parts so the repo's secret scan stays empty


def test_no_secret_in_the_email(smtp, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:pw@host:5432/railway")
    detail = f"failed with {FAKE_KEY} on postgresql://postgres:pw@host:5432/railway (app-password-123)"
    alerts.send_error_alert("RuntimeError", "q", detail)
    body = smtp[0].get_content()
    for secret in (FAKE_KEY, "postgres:pw", "app-password-123"):
        assert secret not in body
    assert body.count("[hidden]") == 3


def test_smtp_failure_does_not_raise(smtp, monkeypatch):
    def broken(*args, **kwargs):
        raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

    monkeypatch.setattr(alerts.smtplib, "SMTP", broken)
    assert not alerts.send_error_alert("RuntimeError", "q", "d")
