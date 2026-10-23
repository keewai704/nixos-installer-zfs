"""Shared, side-effect-free validation for the wizard and privileged worker."""

import re

LOCALES = {"日本語": "ja_JP.UTF-8", "English": "en_US.UTF-8"}
KEYBOARDS = {"US": "us", "日本語 (JIS)": "jp"}
TIMEZONES = ["Asia/Tokyo", "UTC", "America/New_York", "America/Los_Angeles", "Europe/London", "Europe/Berlin"]


def validate(request):
    if not isinstance(request, dict):
        raise ValueError("Invalid installation request")
    required = {"disk", "identity", "hostname", "username", "password", "locale", "keyboard", "timezone", "confirmation"}
    if set(request) != required or not all(isinstance(v, str) for v in request.values()):
        raise ValueError("Invalid installation fields")
    if not re.fullmatch(r"/dev/[a-zA-Z0-9_/-]{1,200}", request["disk"]):
        raise ValueError("Select a disk")
    if not re.fullmatch(r"[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", request["hostname"]):
        raise ValueError("Invalid hostname")
    username = request["username"]
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,30}", username) or re.fullmatch(r"root|nobody|greeter|nixbld[0-9]*", username):
        raise ValueError("Invalid username")
    password = request["password"]
    if not 8 <= len(password) <= 1024 or any(ord(c) < 32 or ord(c) == 127 for c in password):
        raise ValueError("Use a password of 8–1024 characters without control characters")
    if request["locale"] not in LOCALES.values() or request["keyboard"] not in KEYBOARDS.values() or request["timezone"] not in TIMEZONES:
        raise ValueError("Invalid regional settings")
    if request["confirmation"] != "ERASE " + request["disk"]:
        raise ValueError("The disk erase confirmation does not match")
    if not request["identity"] or len(request["identity"]) > 512:
        raise ValueError("Invalid disk identity")
    return request
