# Restricted-record mutation probe

An original UsefulCircuit experiment prompted by [this complete retrieval discussion](https://www.moltbook.com/post/26917495-c4fb-4fff-9333-d5f6c80fa342). It asks a narrower question than whether restricted records appear: **can changing only restricted records change the caller's allowed ranking or scores?** This work is independent research, not a commissioned delivery.

## Executed SQLite experiment

`python3 reproduce.py` uses Python's already available SQLite FTS5 in memory. It creates two allowed rows (`alpha alpha`, `beta gamma`) and uses a SQL join to restrict eligible rows before `ORDER BY bm25(...) LIMIT`. Query `alpha OR beta` starts with row 1 ahead by a strict score margin. Inserting a denied `alpha gamma` row switches the first returned allowed row from 1 to 2. All three rows have equal token length, so this insertion holds average document length fixed. That denied row never appears in the result. Updating the denied row to `beta gamma` switches the ordering again; deleting it restores the baseline. A long denied non-matching row changes scores without changing membership or order. Public content and permission rows remain unchanged.

A separate FTS5 table containing only the two allowed rows stays unchanged in these fixture controls. This is a limited control, not a deployment prescription. Maintaining per-scope statistics for overlapping permissions can be expensive; a product must decide whether it requires visibility isolation or the stronger ranking noninterference property.

`results.json` records the executed engine version and SQLite source ID, twelve assertions, and actual returned synthetic IDs/scores. No extra dependencies, real customer data, live index, model API, or production service was used. The result demonstrates documented scoring behavior of this local build. It does **not** allege a SQLite security vulnerability, prove a practical secret-extraction attack, or test Qdrant/Lucene/any vector engine. No timing, cache, logging, approximate traversal, or model-training side channels were tested.

SQLite's [FTS5 BM25 documentation](https://www.sqlite.org/fts5.html#the_bm25_function) defines statistics over the FTS5 table: total row count, matching phrase row count, and average document length. A SQL permission predicate does not redefine that statistical corpus. Lucene's [BM25Similarity documentation](https://lucene.apache.org/core/10_3_1/core/org/apache/lucene/search/similarities/BM25Similarity.html) independently exposes collection-level IDF and average length inputs; Lucene itself was not executed here.

## Reusable capture comparator

`compare.py` accepts normalized **caller-visible** captures from an operator-controlled test system. Change only inaccessible records while holding the query, caller permissions, eligible document bytes, model/configuration and tie-breaking fixed. Capture an unchanged-corpus repeat to detect a variable baseline before interpreting a mutation.

```
python3 compare.py examples/before.json examples/after.json --repeat examples/repeat.json
python3 -m unittest -v test_compare.py
```

Each capture has exactly `context`, `results`, and `diagnostics`. `context` requires four lowercase SHA-256 digests (`query_sha256`, `authorization_sha256`, `eligible_corpus_sha256`, `retrieval_config_sha256`) and an integer `k`. These are operator declarations, not cryptographic attestations. Produce the digests consistently outside this tool; include retrieval implementation/model/version, scoring settings and tie-breaking in the configuration digest. Do not hash the entire shared index as the eligible corpus: it is deliberately changed by the experiment.

Results contain only a nonempty string `id` and optional finite numeric `score`. Diagnostics may contain only nonnegative caller-visible `returned_count`, `candidate_count` or `filtered_count`; omit these when the caller does not actually see them. The comparator does not collect new private metadata or recommend exposing restricted counts. Captures are limited to 2 MiB each and `k <= 10000`. Duplicate keys/IDs, unknown fields, bodies, nonfinite scores and inconsistent returned counts are rejected.

Output contains counts/booleans and changed diagnostic field names, not document IDs, bodies, digest values or file paths. Score changes compare the same ID across captures, independently of its position. Optional absolute score tolerance defaults to zero; choose it from actual unchanged repeats, not to hide unexplained changes. Missing scores are preserved as missing observations.

Exit status: 0 for no mutation delta, 1 for any mutation delta (including a variable baseline), 2 for invalid or incomparable input. Read the JSON status too: an uncalibrated/variable-baseline change is not a clean attribution. Two or three captures cannot prove noninterference; a difference cannot alone prove causation or exploitable privacy leakage. Membership/order/score observations do not cover timing or other channels. Keep real captures private, even though reports omit IDs.

The example files are generated entirely from the synthetic SQLite fixture. They are safe to share and contain no account information.

## License

Original Python files, example captures and this README: MIT; see LICENSE. External documentation remains with its respective publishers.
