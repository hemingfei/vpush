# IMA Library Performance Design

## Goal

Keep report-library catalog and first-page requests responsive while background database and remote-archive maintenance run, without adding dependencies, WAL, caches, Redis, or extra workers.

## Scope

1. Add a short-lived SQLite `mode=ro` query path for request-time reads that currently wait on `DB._lock`: authentication user lookup, IMA settings/config, IMA ACL reads, IMA read-index metadata/page/detail/catalog/count reads. `:memory:` databases keep the shared connection for tests. SQLite `busy_timeout=5000` remains; this removes Python-lock waiting but does not bypass SQLite file locks.
2. For remote storage only, persist the source fingerprint after filename restore, manifest repair, and retag all finish without error. A matching checkpoint skips those three operations on later starts. Local storage behavior is unchanged. Index validation still runs before the check, and optional FTS sync still runs after it.
3. Mount the report-list surface and skeleton synchronously before catalog/documents requests settle. Reader routes remain separate; ACL and stale-route checks remain unchanged.
4. Replace catalog window sorting with one grouped count query plus one indexed latest-row lookup per authorized group, using existing `idx_ima_doc_group_latest`.

## Safety

- ACL predicates and returned payloads do not change.
- Read-only connections are opened per call and closed immediately, so database replacement cannot leave a connection on an old inode.
- Maintenance checkpoint advances only after all attempted maintenance operations succeed. Missing or stale checkpoints preserve current behavior.
- Existing metadata search remains active while SemiAnalysis FTS is disabled.

## Validation

- A file-backed IMA query completes while the shared Python lock is deliberately held; memory databases still work.
- Existing ACL integration tests remain green.
- Remote maintenance skips NFS work only for a matching successful checkpoint and retries after failure.
- Frontend source contract proves list shell mounting occurs before API creation/await.
- Catalog semantics cover empty sort dates, tie ordering, multiple and empty groups; query plan uses the existing grouped latest index without a window sort.
- Run focused tests, full test suite, production-size SQLite benchmark, mechanical frontend detector, and independent review.
