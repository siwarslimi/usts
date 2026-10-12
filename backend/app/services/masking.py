"""Remove phone numbers and IBANs before any content is sent to the AI provider."""
import re

IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}(?:[ ]?[A-Z0-9]{1,3})?\b")
# French and international formats: 06 12 34 56 78, 06.12.34.56.78, +33 6 12 34 56 78, 0033612345678
PHONE_RE = re.compile(r"(?<![\w+])(?:(?:\+|00)\d{2,3}[\s.-]?(?:\(0\)[\s.-]?)?|0)[1-9](?:[\s.-]?\d{2}){4}(?![\w])")
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")


def mask_sensitive(text: str) -> str:
    text = IBAN_RE.sub("[IBAN masqué]", text)
    text = PHONE_RE.sub("[téléphone masqué]", text)
    return text


def redact_email(address: str) -> str:
    """For logs: keep the domain, hide the local part."""
    local, _, domain = address.partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"
