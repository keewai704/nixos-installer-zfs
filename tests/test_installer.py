"""Validate the destructive worker's trust boundary without touching devices."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "installer"))
from model import validate


class RequestValidation(unittest.TestCase):
    def request(self):
        return dict(disk="/dev/vda", identity="254:0 42949672960 test-disk",
                    hostname="test-host", username="testuser", password="fixture-only-password",
                    locale="ja_JP.UTF-8", keyboard="jp", timezone="Asia/Tokyo",
                    confirmation="ERASE /dev/vda")

    def test_accepts_complete_explicit_request(self):
        validate(self.request())

    def test_rejects_mismatched_erase_and_injected_or_reserved_fields(self):
        bad = {
            "disk": ["/dev/vda;reboot", "/dev/vda\n", "/tmp/disk"],
            "hostname": ['${builtins.abort "injected"}', "x\nservices.openssh.enable = true;"],
            "username": ["root", "greeter", "nixbld1", "a.b", "user\n"],
            "password": ["short", "secret\nnext-line", "secret\x00value"],
            "locale": ["invalid"], "keyboard": ["x;reboot"], "timezone": ["../../etc/shadow"],
            "identity": [""], "confirmation": ["ERASE /dev/vdb", "YES", "ERASE /dev/vda "],
        }
        for field, values in bad.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    request = self.request()
                    request[field] = value
                    with self.assertRaises(ValueError):
                        validate(request)

    def test_rejects_missing_extra_and_non_string_fields(self):
        request = self.request()
        del request["confirmation"]
        with self.assertRaises(ValueError):
            validate(request)
        request = self.request() | {"command": "reboot"}
        with self.assertRaises(ValueError):
            validate(request)
        for value in (None, [], True, 123):
            with self.assertRaises(ValueError):
                validate(value)
            with self.assertRaises(ValueError):
                validate(self.request() | {"identity": value})


if __name__ == "__main__":
    unittest.main()
