"""Compare normalized caller-visible retrieval captures without echoing content.

This is an observation tool. Metadata is operator-declared, not attested.
No network, pickle, dynamic imports, model inference, or service writes.
"""
import argparse
import json
import math
import re
import sys
from pathlib import Path

MAX_BYTES = 2 * 1024 * 1024
FIELDS = {"query_sha256", "authorization_sha256", "eligible_corpus_sha256",
          "retrieval_config_sha256", "k"}
DIAGNOSTICS = {"returned_count", "candidate_count", "filtered_count"}


class CaptureError(ValueError):
    pass


def fail(message):
    # Static messages: never include supplied strings or filesystem paths.
    raise CaptureError(message)


def pairs_unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            fail("duplicate JSON key")
        out[key] = value
    return out


def validate(capture):
    if not isinstance(capture, dict) or set(capture) != {"context", "results", "diagnostics"}:
        fail("capture requires exactly context, results, diagnostics")
    context = capture["context"]
    if not isinstance(context, dict) or set(context) != FIELDS:
        fail("invalid context fields")
    for field in FIELDS - {"k"}:
        value = context[field]
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            fail("invalid context digest")
    k = context["k"]
    if type(k) is not int or not 1 <= k <= 10000:
        fail("k must be an integer from 1 to 10000")
    results = capture["results"]
    if not isinstance(results, list) or len(results) > k:
        fail("invalid result count")
    ids = set()
    for result in results:
        if not isinstance(result, dict) or set(result) not in ({"id"}, {"id", "score"}):
            fail("result accepts only id and optional score")
        identifier = result["id"]
        if not isinstance(identifier, str) or not identifier or len(identifier) > 1024:
            fail("invalid result id")
        if identifier in ids:
            fail("duplicate result id")
        ids.add(identifier)
        if "score" in result:
            score = result["score"]
            if type(score) not in (float, int):
                fail("score must be a finite number")
            try:
                finite = math.isfinite(score)
            except OverflowError:
                finite = False
            if not finite:
                fail("score must be a finite number")
    diagnostics = capture["diagnostics"]
    if not isinstance(diagnostics, dict) or not set(diagnostics) <= DIAGNOSTICS:
        fail("unsupported diagnostic")
    if any(type(v) is not int or v < 0 for v in diagnostics.values()):
        fail("diagnostics must be nonnegative integers")
    if "returned_count" in diagnostics and diagnostics["returned_count"] != len(results):
        fail("returned_count conflicts with result count")
    return capture


def load(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        fail("capture exceeds 2 MiB")
    try:
        value = json.loads(raw, object_pairs_hook=pairs_unique,
                           parse_constant=lambda _: fail("nonfinite JSON value"))
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        fail("invalid JSON capture")
    return validate(value)


def delta(before, after, tolerance=0.0):
    left, right = before["results"], after["results"]
    ids_left, ids_right = [r["id"] for r in left], [r["id"] for r in right]
    by_left, by_right = {r["id"]: r for r in left}, {r["id"]: r for r in right}
    common = set(ids_left) & set(ids_right)
    scores_changed = []
    availability_changed = 0
    for identifier in common:
        l, r = by_left[identifier], by_right[identifier]
        if ("score" in l) != ("score" in r):
            availability_changed += 1
        elif "score" in l and not math.isclose(l["score"], r["score"],
                                               rel_tol=0, abs_tol=tolerance):
            scores_changed.append(identifier)
    changed_diagnostics = sorted(k for k in DIAGNOSTICS
                                 if before["diagnostics"].get(k) != after["diagnostics"].get(k))
    out = {"membership_changed": set(ids_left) != set(ids_right),
           "order_changed": ids_left != ids_right,
           "added_count": len(set(ids_right) - set(ids_left)),
           "removed_count": len(set(ids_left) - set(ids_right)),
           "common_score_changes": len(scores_changed),
           "score_availability_changes": availability_changed,
           "diagnostics_changed": changed_diagnostics}
    out["any_change"] = any((out["membership_changed"], out["order_changed"],
                             out["common_score_changes"], out["score_availability_changes"],
                             changed_diagnostics))
    return out


def compare(before, after, repeat=None, tolerance=0.0):
    for capture in (before, after, repeat):
        if capture is not None:
            validate(capture)
    if type(tolerance) not in (float, int) or not math.isfinite(tolerance) or tolerance < 0:
        fail("invalid score tolerance")
    if before["context"] != after["context"] or (repeat is not None
            and repeat["context"] != before["context"]):
        return {"status": "incomparable", "reason": "declared fixed context changed"}
    change = delta(before, after, tolerance)
    baseline = delta(before, repeat, tolerance) if repeat is not None else None
    if baseline and baseline["any_change"]:
        status = "baseline_variable"
    elif repeat is None:
        status = "uncalibrated_change" if change["any_change"] else "uncalibrated_no_change"
    else:
        status = "change_observed" if change["any_change"] else "no_change_observed"
    return {"status": status, "mutation_delta": change, "baseline_delta": baseline,
            "interpretation": "Finite captures only. Context is operator-declared. "
                              "A change is not proof of privacy leakage or causation; "
                              "no change is not proof of noninterference."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("--repeat", help="unchanged-corpus repeat capture")
    parser.add_argument("--score-tolerance", type=float, default=0.0)
    args = parser.parse_args()
    try:
        result = compare(load(args.before), load(args.after),
                         load(args.repeat) if args.repeat else None, args.score_tolerance)
    except CaptureError as error:
        print(json.dumps({"status": "invalid_capture", "reason": str(error)}))
        return 2
    except (OSError, ValueError, RecursionError):
        print(json.dumps({"status": "invalid_capture", "reason": "cannot read capture"}))
        return 2
    print(json.dumps(result, indent=2, allow_nan=False))
    return 2 if result["status"] == "incomparable" else 1 if result["mutation_delta"]["any_change"] else 0


if __name__ == "__main__":
    sys.exit(main())
