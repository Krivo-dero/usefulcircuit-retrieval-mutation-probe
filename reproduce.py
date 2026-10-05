"""Original in-memory SQLite FTS5 experiment; no external data or services."""
import json
import sqlite3


QUERY = "alpha OR beta"


def create():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE VIRTUAL TABLE docs USING fts5(body)")
    db.execute("CREATE VIRTUAL TABLE scoped USING fts5(body)")
    db.execute("CREATE TABLE allowed(id INTEGER PRIMARY KEY)")
    for table in ("docs", "scoped"):
        db.executemany(f"INSERT INTO {table}(rowid,body) VALUES(?,?)",
                       [(1, "alpha alpha"), (2, "beta gamma")])
    db.executemany("INSERT INTO allowed VALUES(?)", [(1,), (2,)])
    return db


def retrieve(db, scoped=False, limit=2):
    # Both variants exclude restricted rows before ORDER BY / LIMIT.
    # The shared table's bm25() still uses table-wide statistics.
    table = "scoped" if scoped else "docs"
    return [dict(id=str(row[0]), score=row[1]) for row in db.execute(
        f"SELECT {table}.rowid, bm25({table}) FROM {table} "
        f"JOIN allowed ON allowed.id={table}.rowid "
        f"WHERE {table} MATCH ? "
        f"ORDER BY bm25({table}),{table}.rowid LIMIT ?", (QUERY, limit))]


def public_snapshot(db):
    return list(db.execute("SELECT docs.rowid,body FROM docs JOIN allowed "
                           "ON allowed.id=docs.rowid ORDER BY docs.rowid"))


def experiment():
    checks = []
    observations = {}
    with create() as db:
        original = public_snapshot(db)
        baseline = retrieve(db)
        scoped_baseline = retrieve(db, scoped=True)
        checks.append(("unchanged_repeat", retrieve(db) == baseline))
        checks.append(("baseline_has_strict_score_margin", baseline[0]["score"]
                       < baseline[1]["score"]))
        # Equal-length insert: average length stays fixed; phrase statistics change.
        db.execute("INSERT INTO docs(rowid,body) VALUES(3,'alpha gamma')")
        inserted = retrieve(db)
        observations["restricted_insert"] = {"before": baseline, "after": inserted}
        checks.append(("insert_changes_first_public_hit", baseline[0]["id"] == "1"
                       and inserted[0]["id"] == "2"))
        checks.append(("restricted_row_never_returned", all(x["id"] in {"1", "2"}
                       for x in inserted)))
        checks.append(("public_content_unchanged", public_snapshot(db) == original))
        checks.append(("separate_scope_insert_control", retrieve(db, scoped=True)
                       == scoped_baseline))
        db.execute("UPDATE docs SET body='beta gamma' WHERE rowid=3")
        updated = retrieve(db)
        observations["restricted_update"] = {"before": inserted, "after": updated}
        checks.append(("update_reverses_public_order", updated[0]["id"] == "1"
                       and updated != inserted))
        checks.append(("separate_scope_update_control", retrieve(db, scoped=True)
                       == scoped_baseline))
        db.execute("DELETE FROM docs WHERE rowid=3")
        checks.append(("delete_restores_baseline", retrieve(db) == baseline))
        # A denied non-matching document can still change length normalization.
        db.execute("INSERT INTO docs(rowid,body) VALUES(3,?)", ("gamma " * 100,))
        unrelated = retrieve(db)
        observations["restricted_nonmatching_insert"] = {
            "before": baseline, "after": unrelated}
        checks.append(("nonmatching_row_changes_scores", unrelated != baseline
                       and [x["id"] for x in unrelated] == [x["id"] for x in baseline]))
        checks.append(("separate_scope_nonmatching_control", retrieve(db, scoped=True)
                       == scoped_baseline))
        checks.append(("public_content_still_unchanged", public_snapshot(db) == original))
        source_id = db.execute("SELECT sqlite_source_id()").fetchone()[0]
    result = {"engine": "SQLite FTS5", "sqlite_version": sqlite3.sqlite_version,
              "sqlite_source_id": source_id, "query": QUERY,
              "all_passed": all(p for _, p in checks), "check_count": len(checks),
              "checks": [{"name": n, "passed": p} for n, p in checks],
              "observations": observations,
              "limits": "Synthetic two-public-row fixture on the recorded SQLite build. "
                        "Not a production exploit, a vector-engine test, or a complete "
                        "side-channel audit. Scope partition is a fixture control, "
                        "not a universal security guarantee."}
    return result


if __name__ == "__main__":
    result = experiment()
    print(json.dumps(result, indent=2, allow_nan=False))
    raise SystemExit(0 if result["all_passed"] else 1)
