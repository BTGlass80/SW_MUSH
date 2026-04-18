"""
Session 46 regression test — encounter choice button dispatches via 'respond'.

Bug observed: server sent a space_choices frame with choices like
{key: "comply", label: "Submit to inspection", ...}; clicking the
"COMPLY" button in the web client sent the bare string "comply" over
the WS, and the server replied "Huh? Unknown command: 'comply'". The
server dispatches encounter choices through RespondCommand (parser/
encounter_commands.py), so the correct payload is 'respond comply'.

This test grep-inspects static/client.html to confirm the click handler
in handleSpaceChoices sends 'respond ' + <key|index|...>. It's a text
check rather than a live DOM test because spinning up a headless
browser in CI for this one assertion is overkill — the shape we're
protecting against ("sendCmd('comply')") is exactly detectable by
pattern.

If a future refactor drops the 'respond ' prefix or reintroduces the
bare-key pattern, this test will fail before the server boots.
"""
import os
import re
import unittest


HERE = os.path.dirname(os.path.abspath(__file__))
# tests/ lives at project root; client.html is at static/client.html
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
CLIENT_HTML = os.path.join(PROJECT_ROOT, "static", "client.html")


class EncounterChoiceDispatchTests(unittest.TestCase):
    """Lock the client-side contract: encounter choices send 'respond <key>'."""

    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(CLIENT_HTML):
            raise unittest.SkipTest(f"client.html not found at {CLIENT_HTML}")
        with open(CLIENT_HTML, encoding="utf-8") as f:
            cls.client_html = f.read()

    def test_handle_space_choices_exists(self):
        """Sanity: the function we're guarding must still exist."""
        self.assertIn("function handleSpaceChoices(msg)", self.client_html)

    def test_respond_prefix_is_used_in_handle_space_choices(self):
        """
        Extract the body of handleSpaceChoices and assert it emits a
        'respond ' prefixed command. Uses a brace-counting scan rather
        than a greedy regex so nested functions / closures don't confuse
        the extraction.
        """
        marker = "function handleSpaceChoices(msg)"
        start = self.client_html.find(marker)
        self.assertNotEqual(start, -1, "handleSpaceChoices marker not found")
        # Find the opening brace after the parameter list
        brace_open = self.client_html.find("{", start)
        self.assertNotEqual(brace_open, -1)
        # Scan forward counting braces to find the matching close
        depth = 0
        end = brace_open
        for i in range(brace_open, len(self.client_html)):
            ch = self.client_html[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        body = self.client_html[brace_open:end]
        self.assertIn(
            "sendCmd('respond ",
            body,
            "handleSpaceChoices must dispatch via sendCmd('respond ' + key). "
            "Sending the bare choice key produces 'Huh? Unknown command' "
            "because there is no top-level 'comply' / 'bluff' / 'run' / etc "
            "command — the server dispatches through RespondCommand.",
        )

    def test_bare_key_dispatch_pattern_is_gone(self):
        """
        Guard against the specific shape of the old bug. The old line was:
            sendCmd(c.key || c.cmd || c.label);
        (no 'respond ' prefix). If someone reintroduces that exact shape,
        fail loudly.
        """
        # The pattern we're forbidding: sendCmd called with c.key directly
        # as first argument without a 'respond ' string concatenation.
        forbidden = re.compile(
            r"sendCmd\s*\(\s*c\.key\s*\|\|", re.MULTILINE
        )
        # Only flag if the call site is NOT immediately preceded (within
        # ~80 chars) by 'respond '. We build a window check.
        for m in forbidden.finditer(self.client_html):
            window_start = max(0, m.start() - 120)
            window = self.client_html[window_start : m.end() + 30]
            self.assertIn(
                "respond ",
                window,
                f"Found sendCmd(c.key || …) at offset {m.start()} without "
                "a nearby 'respond ' prefix. This is the regression from "
                "Session 46 — encounter choices must be dispatched via "
                "'respond <key>'.",
            )


if __name__ == "__main__":
    unittest.main()
