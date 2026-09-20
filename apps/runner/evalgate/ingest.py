"""Ingest a JSONL of task cases into a suite.

Tolerant on input, strict on what lands in the database. Re-running the same
file is a no-op plus updates: the (suiteId, externalId) unique constraint makes
this idempotent, so you can fix a rubric and re-ingest without duplicating.
"""
from __future__ import annotations
import argparse, asyncio, json, os, sys
from pathlib import Path
from typing import Any

import asyncpg


def parse_line(line: str, lineno: int) -> dict[str, Any]:
    try:
        rec = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ValueError(f"line {lineno}: invalid JSON ({exc.msg})") from exc

    if not isinstance(rec, dict):
        raise ValueError(f"line {lineno}: expected a JSON object, got {type(rec).__name__}")

    prompt = rec.get("prompt")
    if not prompt or not isinstance(prompt, str):
        raise ValueError(f"line {lineno}: missing or non-string 'prompt'")

    # A recorded trajectory rides inside `expected` so the worker's replay
    # path finds it without a second column.
    expected = rec.get("expected") or {}
    if not isinstance(expected, dict):
        raise ValueError(f"line {lineno}: 'expected' must be an object")
    if "trajectory" in rec:
        if not isinstance(rec["trajectory"], dict):
            raise ValueError(f"line {lineno}: 'trajectory' must be an object")
        expected = {**expected, "trajectory": rec["trajectory"]}

    tags = rec.get("tags") or []
    if not isinstance(tags, list) or any(not isinstance(t, str) for t in tags):
        raise ValueError(f"line {lineno}: 'tags' must be a list of strings")

    ground_truth = rec.get("ground_truth")
    if ground_truth is not None and not isinstance(ground_truth, dict):
        raise ValueError(f"line {lineno}: 'ground_truth' must be an object")

    return {
        "external_id": str(rec.get("id") or rec.get("external_id") or f"case-{lineno}"),
        "prompt": prompt,
        "expected": json.dumps(expected) if expected else None,
        "rubric": rec.get("rubric"),
        "tags": tags,
        "ground_truth": json.dumps(ground_truth) if ground_truth else None,
        "_has_trajectory": "trajectory" in expected,
    }


def read_file(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"no such file: {path}")

    rows: list[dict[str, Any]] = []
    errors: list[str] = []

    with path.open() as fh:
        for i, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                rows.append(parse_line(line, i))
            except ValueError as exc:
                errors.append(str(exc))

    if errors:
        print(f"{len(errors)} malformed record(s):", file=sys.stderr)
        for e in errors[:20]:
            print(f"  {e}", file=sys.stderr)
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more", file=sys.stderr)
        # All or nothing. A half-ingested suite is worse than no suite,
        # because the run that follows silently evaluates the wrong N.
        raise SystemExit("nothing imported")

    if not rows:
        raise SystemExit("file contained no records")

    seen: set[str] = set()
    dupes: list[str] = []
    for r in rows:
        if r["external_id"] in seen:
            dupes.append(r["external_id"])
        seen.add(r["external_id"])
    if dupes:
        raise SystemExit(
            f"duplicate ids within the file: {sorted(set(dupes))[:10]} "
            f"({len(set(dupes))} distinct). Fix the file or drop the id field."
        )

    return rows


async def ingest(
    path: Path,
    slug: str,
    name: str | None,
    dsn: str,
    dry_run: bool = False,
    prune: bool = False,
) -> None:
    rows = read_file(path)
    replay = sum(1 for r in rows if r["_has_trajectory"])
    with_gt = sum(1 for r in rows if r["ground_truth"])
    with_rubric = sum(1 for r in rows if r["rubric"])

    print(f"parsed {len(rows)} cases from {path.name}")
    print(f"  {replay} with recorded trajectories (replay mode, no model calls)")
    print(f"  {with_gt} with ground truth")
    print(f"  {with_rubric} with rubrics")

    if dry_run:
        print("\ndry run, nothing written. Sample:")
        s = rows[0]
        print(json.dumps({k: v for k, v in s.items() if not k.startswith("_")}, indent=2)[:1200])
        return

    con = await asyncpg.connect(dsn)
    try:
        async with con.transaction():
            suite_id = await con.fetchval(
                'INSERT INTO "Suite" (id, slug, name) '
                "VALUES (gen_random_uuid()::text, $1, $2) "
                "ON CONFLICT (slug) DO UPDATE SET "
                '  name = EXCLUDED.name, version = "Suite".version + 1 '
                "RETURNING id",
                slug,
                name or slug,
            )

            await con.executemany(
                'INSERT INTO "TaskCase" '
                '  (id, "suiteId", "externalId", prompt, expected, rubric, tags, "groundTruth") '
                "VALUES (gen_random_uuid()::text, $1, $2, $3, $4::jsonb, $5, $6, $7::jsonb) "
                'ON CONFLICT ("suiteId", "externalId") DO UPDATE SET '
                "  prompt = EXCLUDED.prompt, "
                "  expected = EXCLUDED.expected, "
                "  rubric = EXCLUDED.rubric, "
                "  tags = EXCLUDED.tags, "
                '  "groundTruth" = EXCLUDED."groundTruth"',
                [
                    (
                        suite_id,
                        r["external_id"],
                        r["prompt"],
                        r["expected"],
                        r["rubric"],
                        r["tags"],
                        r["ground_truth"],
                    )
                    for r in rows
                ],
            )

            removed = 0
            if prune:
                # Only safe before any run references the case. Deleting a case
                # with trajectories would orphan scores, so we scope the delete.
                deleted = await con.fetch(
                    'DELETE FROM "TaskCase" tc '
                    'WHERE tc."suiteId" = $1 '
                    "  AND NOT (tc.\"externalId\" = ANY($2::text[])) "
                    '  AND NOT EXISTS (SELECT 1 FROM "Trajectory" t WHERE t."taskCaseId" = tc.id) '
                    "RETURNING tc.id",
                    suite_id,
                    [r["external_id"] for r in rows],
                )
                removed = len(deleted)

            total = await con.fetchval(
                'SELECT COUNT(*) FROM "TaskCase" WHERE "suiteId" = $1', suite_id
            )
            version = await con.fetchval('SELECT version FROM "Suite" WHERE id = $1', suite_id)

        print(f"\nsuite '{slug}' ({suite_id}) now at version {version}")
        print(f"  {len(rows)} upserted, {total} total in suite")
        if prune:
            print(f"  {removed} stale cases pruned")
        print(f"\nstart a run:")
        print(
            '  curl -s localhost:4000/graphql -H \'content-type: application/json\' \\\n'
            f'    -d \'{{"query":"mutation{{ startRun(suiteSlug:\\"{slug}\\", '
            'model:\\"mock-model\\"){ id totalCases } }"}\''
        )
    finally:
        await con.close()


def main() -> None:
    p = argparse.ArgumentParser(
        prog="evalgate-ingest",
        description="Import a JSONL of task cases into an EvalGate suite.",
    )
    p.add_argument("file", type=Path, help="path to .jsonl")
    p.add_argument("--slug", required=True, help="suite slug, e.g. swebench-200")
    p.add_argument("--name", help="human-readable suite name")
    p.add_argument("--dsn", default=os.getenv("DATABASE_URL"))
    p.add_argument("--dry-run", action="store_true", help="parse and report, write nothing")
    p.add_argument(
        "--prune",
        action="store_true",
        help="delete suite cases absent from the file (skips any already used in a run)",
    )
    a = p.parse_args()

    if not a.dsn:
        raise SystemExit("set DATABASE_URL or pass --dsn")

    asyncio.run(ingest(a.file, a.slug, a.name, a.dsn, a.dry_run, a.prune))


if __name__ == "__main__":
    main()