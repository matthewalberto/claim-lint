import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import claim_lint as cl  # noqa: E402

EXAMPLES = os.path.join(ROOT, "examples")
RULES_MD = os.path.join(EXAMPLES, "rules.example.md")
RULES_YML = os.path.join(EXAMPLES, "rules.example.yml")
DRAFT = os.path.join(EXAMPLES, "draft.md")


def run(argv, stdin_text=""):
    out = io.StringIO()
    code = cl.main(argv, stdin=io.StringIO(stdin_text), stdout=out)
    return code, out.getvalue()


def rules(*rows):
    head = "| pattern | why | instead |\n|---|---|---|\n"
    return cl.parse_markdown_rules(head + "\n".join("| %s | %s | %s |" % r for r in rows))


class PatternTests(unittest.TestCase):
    def test_phrase_is_case_insensitive_and_whole_word(self):
        rx = cl.compile_pattern("never makes mistakes")
        self.assertTrue(rx.search("It Never  Makes Mistakes."))
        self.assertFalse(rx.search("it nevermakes mistakes"))

    def test_phrase_does_not_match_inside_a_longer_word(self):
        rx = cl.compile_pattern("award-winning")
        self.assertTrue(rx.search("our award-winning app"))
        self.assertFalse(rx.search("our award-winnings"))

    def test_star_matches_word_endings(self):
        rx = cl.compile_pattern("guarantee* funding")
        for s in ("guarantee funding", "guaranteed funding", "guarantees funding"):
            self.assertTrue(rx.search(s), s)

    def test_slash_pattern_is_a_regex(self):
        rx = cl.compile_pattern(r"/\bHIPAA[- ]certified\b/")
        self.assertTrue(rx.search("We are HIPAA-certified"))
        self.assertTrue(rx.search("hipaa certified"))

    def test_punctuation_is_literal_in_phrases(self):
        rx = cl.compile_pattern("100% accurate")
        self.assertTrue(rx.search("It is 100% accurate."))
        self.assertFalse(rx.search("It is 1000 accurate."))

    def test_bad_regex_is_a_rules_error(self):
        with self.assertRaises(cl.RulesError):
            cl.compile_pattern("/(unclosed/")


class RulesFileTests(unittest.TestCase):
    def test_example_markdown_loads_every_row(self):
        rs = cl.load_rules(RULES_MD)
        self.assertEqual(len(rs), 9)
        hipaa = [r for r in rs if "HIPAA" in r.pattern][0]
        self.assertIn("certification", hipaa.why)
        self.assertTrue(hipaa.instead)

    def test_pipe_inside_code_span_stays_in_the_cell(self):
        rs = cl.load_rules(RULES_MD)
        endorsed = [r for r in rs if "endorsed" in r.pattern][0]
        self.assertTrue(endorsed.regex.search("endorsed by the ministry"))
        self.assertIn("No regulator", endorsed.why)

    def test_org_filter(self):
        everyone = cl.load_rules(RULES_MD)
        marketing = cl.load_rules(RULES_MD, org="marketing")
        self.assertEqual(len(marketing), len(everyone) - 1)  # drops the grants-team row
        self.assertTrue(any(r.org == "marketing" for r in marketing))
        self.assertFalse(any(r.org == "grants-team" for r in marketing))

    def test_alternative_header_names(self):
        text = "| Claim | Reason | Safe alternative |\n|:--|:--|:--|\n| best in class | vague | specific |\n"
        rs = cl.parse_markdown_rules(text)
        self.assertEqual(len(rs), 1)
        self.assertEqual(rs[0].why, "vague")
        self.assertEqual(rs[0].instead, "specific")

    def test_struck_through_rows_are_skipped(self):
        rs = rules(("~~old claim~~", "lifted", ""), ("live claim", "x", ""))
        self.assertEqual([r.pattern for r in rs], ["live claim"])

    def test_tables_without_a_pattern_column_are_ignored(self):
        text = "| name | date |\n|---|---|\n| a | b |\n"
        self.assertEqual(cl.parse_markdown_rules(text), [])

    def test_empty_rules_file_is_an_error(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
            fh.write("# nothing here\n")
        try:
            with self.assertRaises(cl.RulesError):
                cl.load_rules(fh.name)
        finally:
            os.unlink(fh.name)

    def test_yaml_rules(self):
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest("PyYAML not installed")
        rs = cl.load_rules(RULES_YML)
        self.assertEqual(len(rs), 4)


class ScanTests(unittest.TestCase):
    def test_example_draft_hits(self):
        hits = cl.scan_paths([DRAFT], cl.load_rules(RULES_MD))
        labels = sorted(h.label for h in hits)
        self.assertEqual(len(hits), 4, [(h.line, h.label) for h in hits])
        self.assertTrue(any("guaranteed compliance" in l for l in labels))
        self.assertTrue(any("HIPAA" in l for l in labels))
        self.assertTrue(any("never makes mistakes" in l for l in labels))
        self.assertTrue(any("guarantee" in l and "funding" in l for l in labels))

    def test_phrase_wrapped_across_lines_is_found_once(self):
        hits = cl.scan_text("records, with guaranteed\ncompliance for all", rules(("guaranteed compliance", "", "")))
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].line, 1)

    def test_same_line_match_is_not_double_counted(self):
        text = "guaranteed compliance here\nand more text"
        hits = cl.scan_text(text, rules(("guaranteed compliance", "", "")))
        self.assertEqual(len(hits), 1)

    def test_html_comments_are_skipped_but_keep_line_numbers(self):
        text = "<!-- 100% accurate -->\nline two\n<!--\n100% accurate\n-->\nwe are 100% accurate"
        hits = cl.scan_text(text, rules(("100% accurate", "", "")), html=True)
        self.assertEqual([h.line for h in hits], [6])

    def test_keep_comments_checks_comments_too(self):
        text = "<!-- 100% accurate -->"
        self.assertEqual(len(cl.scan_text(text, rules(("100% accurate", "", "")), html=False)), 1)

    def test_ignore_marker(self):
        text = "We never say 100% accurate.  <!-- claim-lint: ignore -->\nIt is 100% accurate."
        hits = cl.scan_lines(text.splitlines(), rules(("100% accurate", "", "")))
        self.assertEqual([h.line for h in hits], [2])

    def test_folder_scan_walks_text_files_only(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "a.md"), "w", encoding="utf-8") as fh:
            fh.write("100% accurate\n")
        with open(os.path.join(d, "b.png"), "w", encoding="utf-8") as fh:
            fh.write("100% accurate\n")
        os.makedirs(os.path.join(d, "node_modules"))
        with open(os.path.join(d, "node_modules", "c.md"), "w", encoding="utf-8") as fh:
            fh.write("100% accurate\n")
        hits = cl.scan_paths([d], rules(("100% accurate", "", "")))
        self.assertEqual([os.path.basename(h.source) for h in hits], ["a.md"])


class CliTests(unittest.TestCase):
    def test_draft_exits_1_and_prints_reason_and_alternative(self):
        code, out = run(["--rules", RULES_MD, "--file", DRAFT])
        self.assertEqual(code, 1)
        self.assertIn("why:", out)
        self.assertIn("instead:", out)
        self.assertIn("4 banned claim(s)", out)

    def test_clean_text_on_stdin_exits_0(self):
        code, out = run(["--rules", RULES_MD], "Our tool helps your team spot issues early.\n")
        self.assertEqual(code, 0)
        self.assertIn("clean", out)

    def test_stdin_with_hit(self):
        code, _ = run(["--rules", RULES_MD], "It never makes mistakes.\n")
        self.assertEqual(code, 1)

    def test_json_output(self):
        code, out = run(["--rules", RULES_MD, "--file", DRAFT, "--json"])
        self.assertEqual(code, 1)
        data = json.loads(out)
        self.assertEqual(data["count"], 4)
        self.assertEqual(set(data["hits"][0]), {"source", "line", "label", "matched", "text", "why", "instead"})

    def test_org_flag_drops_other_orgs_rules(self):
        code, out = run(["--rules", RULES_MD, "--file", DRAFT, "--org", "marketing", "--json"])
        self.assertEqual(json.loads(out)["count"], 3)

    def test_missing_rules_file_exits_2(self):
        code, _ = run(["--rules", os.path.join(EXAMPLES, "nope.md")], "x")
        self.assertEqual(code, 2)

    def test_missing_input_file_exits_2(self):
        code, _ = run(["--rules", RULES_MD, "--file", os.path.join(EXAMPLES, "nope.md")])
        self.assertEqual(code, 2)

    def test_rules_flag_is_required(self):
        code, _ = run(["--file", DRAFT])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
