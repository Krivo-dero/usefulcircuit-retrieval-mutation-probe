import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from compare import CaptureError, compare, load, validate


def capture():
    return {"context": {"query_sha256": "a" * 64, "authorization_sha256": "b" * 64,
                        "eligible_corpus_sha256": "c" * 64,
                        "retrieval_config_sha256": "d" * 64, "k": 2},
            "results": [{"id": "public-A", "score": 1.0}, {"id": "public-B", "score": 0.8}],
            "diagnostics": {"returned_count": 2}}


class CompareTests(unittest.TestCase):
    def test_stable_repeat_is_scoped_observation(self):
        a = capture()
        r = compare(a, a, a)
        self.assertEqual(r["status"], "no_change_observed")
        self.assertIn("not proof", r["interpretation"])

    def test_rank_swap_and_score_changes(self):
        a, b = capture(), capture()
        b["results"] = [{"id": "public-B", "score": 1.5}, {"id": "public-A", "score": 0.7}]
        r = compare(a, b, a)
        self.assertEqual(r["status"], "change_observed")
        self.assertFalse(r["mutation_delta"]["membership_changed"])
        self.assertTrue(r["mutation_delta"]["order_changed"])
        self.assertEqual(r["mutation_delta"]["common_score_changes"], 2)
        self.assertNotIn("public-A", json.dumps(r))

    def test_displacement_count_only(self):
        a, b = capture(), capture()
        b["results"].pop()
        b["diagnostics"]["returned_count"] = 1
        r = compare(a, b, a)
        self.assertEqual(r["mutation_delta"]["removed_count"], 1)

    def test_missing_repeat_retains_uncertainty(self):
        self.assertEqual(compare(capture(), capture())["status"], "uncalibrated_no_change")

    def test_variable_baseline_prevents_clean_causal_label(self):
        a, b = capture(), capture()
        b["results"].reverse()
        self.assertEqual(compare(a, b, b)["status"], "baseline_variable")

    def test_all_fixed_context_fields_enforced(self):
        for field in capture()["context"]:
            with self.subTest(field=field):
                a, b = capture(), capture()
                b["context"][field] = 3 if field == "k" else "e" * 64
                self.assertEqual(compare(a, b, a)["status"], "incomparable")

    def test_score_tolerance_and_missing_score(self):
        a, b = capture(), capture()
        b["results"][0]["score"] += 0.001
        self.assertFalse(compare(a, b, a, 0.01)["mutation_delta"]["any_change"])
        del b["results"][0]["score"]
        self.assertEqual(compare(a, b, a)["mutation_delta"]["score_availability_changes"], 1)

    def test_body_and_arbitrary_diagnostics_rejected(self):
        for change in (lambda x: x["results"][0].update(body="PRIVATE_SENTINEL"),
                       lambda x: x["diagnostics"].update(private_count=3)):
            a = capture()
            change(a)
            with self.assertRaises(CaptureError) as c:
                validate(a)
            self.assertNotIn("PRIVATE_SENTINEL", str(c.exception))

    def test_duplicate_ids_bool_and_nonfinite_rejected(self):
        for value in (True, float("nan"), float("inf"), 10 ** 400):
            a = capture()
            a["results"][0]["score"] = value
            with self.assertRaises(CaptureError):
                validate(a)
        a = capture()
        a["results"][1]["id"] = a["results"][0]["id"]
        with self.assertRaises(CaptureError):
            validate(a)

    def test_count_consistency_and_bounds(self):
        for change in (lambda x: x["diagnostics"].update(returned_count=0),
                       lambda x: x["context"].update(k=True),
                       lambda x: x["context"].update(k=1)):
            a = capture()
            change(a)
            with self.assertRaises(CaptureError):
                validate(a)

    def test_duplicate_json_key_and_size_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.json"
            path.write_text('{"context":{},"context":{}}')
            with self.assertRaises(CaptureError):
                load(path)
            path.write_bytes(b" " * (2 * 1024 * 1024 + 1))
            with self.assertRaises(CaptureError):
                load(path)

    def test_cli_exit_and_no_payload_echo(self):
        with tempfile.TemporaryDirectory() as directory:
            before, after = Path(directory) / "before.json", Path(directory) / "after.json"
            before.write_text(json.dumps(capture()))
            a = capture()
            a["results"][0]["body"] = "PRIVATE_SENTINEL"
            after.write_text(json.dumps(a))
            r = subprocess.run([sys.executable, str(Path(__file__).with_name("compare.py")),
                                str(before), str(after)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 2)
            self.assertNotIn("PRIVATE_SENTINEL", r.stdout + r.stderr)
            self.assertEqual(json.loads(r.stdout)["status"], "invalid_capture")


if __name__ == "__main__":
    unittest.main()
