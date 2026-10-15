"""Tests for lib/redact.py."""

import unittest

from lib import redact


class RedactSecretsTest(unittest.TestCase):
    def assertRedacted(self, text: str, label: str) -> None:
        out = redact.redact(text)
        self.assertIn(f"[REDACTED:{label}]", out, out)

    def test_aws_access_key_id(self):
        self.assertRedacted("id=AKIAIOSFODNN7EXAMPLE", "secret:aws_access_key_id")

    def test_aws_secret_access_key(self):
        out = redact.redact("aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEYAB")
        self.assertNotIn("wJalrXUtnFEMI", out)
        self.assertTrue(out.startswith("[REDACTED:secret:"), out)

    def test_private_key_block_is_removed_whole(self):
        text = "a\n-----BEGIN RSA PRIVATE KEY-----\nMIIEow\nIBAAKCAQ\n-----END RSA PRIVATE KEY-----\nb"
        self.assertEqual(redact.redact(text), "a\n[REDACTED:secret:private_key_block]\nb")

    def test_private_key_block_without_end_runs_to_end_of_text(self):
        out = redact.redact("-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXk\n")
        self.assertEqual(out, "[REDACTED:secret:private_key_block]")

    def test_github_tokens(self):
        self.assertRedacted("ghp_" + "a" * 36, "secret:github_token")
        self.assertRedacted("github_pat_" + "B" * 30, "secret:github_token")

    def test_slack_token(self):
        self.assertRedacted("xoxb-1234567890-abcdef", "secret:slack_token")

    def test_llm_api_key(self):
        self.assertRedacted("sk-ant-" + "x" * 30, "secret:llm_api_key")

    def test_datadog_key(self):
        self.assertRedacted("DD_API_KEY=" + "0123456789abcdef" * 2, "secret:datadog_key")

    def test_jwt(self):
        self.assertRedacted("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N",
                            "secret:jwt")

    def test_bearer_token(self):
        self.assertRedacted("Authorization: Bearer abcdefghijklmnop1234", "secret:bearer_token")

    def test_url_credentials(self):
        out = redact.redact("postgres://admin:hunter22@db.internal:5432/app")
        self.assertNotIn("hunter22", out)
        self.assertIn("db.internal:5432/app", out)

    def test_credential_assignment(self):
        self.assertRedacted('password: "s3cretValue!"', "secret:credential_assignment")


class RedactPiiTest(unittest.TestCase):
    def test_email(self):
        self.assertEqual(redact.redact("mail dev@example.com now"),
                         "mail [REDACTED:pii:email] now")

    def test_phone(self):
        self.assertIn("[REDACTED:pii:phone]", redact.redact("call +1 415-555-0123"))

    def test_card_number_passing_luhn(self):
        self.assertIn("[REDACTED:pii:card_number]", redact.redact("card 4111 1111 1111 1111"))

    def test_digit_run_failing_luhn_is_kept(self):
        self.assertEqual(redact.redact("ts 1791542714123"), "ts 1791542714123")


class RedactLeavesOrdinaryOutputAloneTest(unittest.TestCase):
    def test_common_tool_output_is_unchanged(self):
        for text in (
            "commit 35749b1bb7c9ad5d8c5ba2dc2da2ce181469c2f4",
            "id 123e4567-e89b-12d3-a456-426614174000",
            "2026-10-15T10:20:30Z ran 42 tests in 1.234s",
            "Plan: 3 to add, 0 to change, 0 to destroy.",
            "version 1.2.3, port 8080",
        ):
            self.assertEqual(redact.redact(text), text)

    def test_empty_text(self):
        self.assertEqual(redact.redact(""), "")


class RedactOverlapTest(unittest.TestCase):
    def test_rules_match_original_text_not_a_rewritten_one(self):
        # The credential assignment and the JWT overlap; both must be covered by one placeholder
        # and no fragment of the token may survive.
        token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N"
        out = redact.redact(f"token={token} tail")
        self.assertNotIn("eyJ", out)
        self.assertNotIn("dozjg", out)
        self.assertTrue(out.endswith(" tail"))
        self.assertEqual(out.count("[REDACTED:"), 1)

    def test_adjacent_secrets_each_redacted(self):
        out = redact.redact("AKIAIOSFODNN7EXAMPLE dev@example.com")
        self.assertEqual(out, "[REDACTED:secret:aws_access_key_id] [REDACTED:pii:email]")


class RedactValueTest(unittest.TestCase):
    def test_nested_strings_redacted_and_shape_kept(self):
        value = {"findings": [{"what": "uses AKIAIOSFODNN7EXAMPLE", "line": 3}], "ok": True}
        out = redact.redact_value(value)
        self.assertEqual(out["findings"][0]["line"], 3)
        self.assertTrue(out["ok"])
        self.assertNotIn("AKIA", out["findings"][0]["what"])


if __name__ == "__main__":
    unittest.main()
