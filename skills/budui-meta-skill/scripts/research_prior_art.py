#!/usr/bin/env python3
"""Query skills.sh and SkillsMP, then normalize candidates without installing skills."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable


SCRIPT_DIR = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("qiaomu_search_skillsmp", SCRIPT_DIR / "search_skillsmp.py")
if SPEC is None or SPEC.loader is None:  # pragma: no cover
    raise RuntimeError("unable to load search_skillsmp.py")
SKILLSMP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SKILLSMP)

ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
SKILLS_SH_RE = re.compile(
    r"(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)@(?P<skill>[^\s]+)\s+"
    r"(?P<installs>[0-9]+(?:\.[0-9]+)?[KMB]?)\s+installs",
    re.IGNORECASE,
)
MULTIPLIERS = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}


def strip_ansi(value: str) -> str:
    return ANSI_RE.sub("", value)


def parse_install_count(value: str) -> int:
    normalized = value.strip().upper()
    suffix = normalized[-1] if normalized and normalized[-1] in MULTIPLIERS else ""
    number = float(normalized[:-1] if suffix else normalized)
    return int(number * MULTIPLIERS.get(suffix, 1))


def parse_skills_sh_output(output: str, query: str) -> list[dict[str, Any]]:
    text = strip_ansi(output)
    candidates: list[dict[str, Any]] = []
    for match in SKILLS_SH_RE.finditer(text):
        repo = match.group("repo").lower()
        skill = match.group("skill")
        display = match.group("installs")
        candidates.append(
            {
                "source": "skills.sh",
                "query": query,
                "owner_repo": repo,
                "skill_name": skill,
                "family_key": f"{repo}:{skill.lower()}",
                "skills_sh_installs": parse_install_count(display),
                "skills_sh_installs_display": display,
                "skills_sh_url": f"https://skills.sh/{repo}/{skill}",
            }
        )
    return candidates


def run_skills_sh(query: str, timeout: float) -> list[dict[str, Any]]:
    completed = subprocess.run(
        ["npx", "--yes", "skills", "find", query],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if completed.returncode != 0:
        detail = strip_ansi(completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"skills.sh query failed ({completed.returncode}): {detail[:500]}")
    candidates = parse_skills_sh_output(completed.stdout, query)
    if not candidates:
        raise RuntimeError("skills.sh returned no parseable candidates")
    return candidates


def run_skillsmp(query: str, args: argparse.Namespace) -> list[dict[str, Any]]:
    request_args = SimpleNamespace(
        query=query,
        page=1,
        limit=args.skillsmp_limit,
        sort=args.skillsmp_sort,
        category=args.category,
        occupation=args.occupation,
        language=args.language,
        timeout=args.timeout,
        retries=args.retries,
        retry_backoff=args.retry_backoff,
        retry_jitter=args.retry_jitter,
    )
    result = SKILLSMP.fetch(request_args)
    output = []
    for candidate in result["candidates"]:
        item = dict(candidate)
        item["query"] = query
        output.append(item)
    return output


def merge_candidates(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    families: dict[str, dict[str, Any]] = {}
    for record in records:
        key = str(record["family_key"])
        family = families.setdefault(
            key,
            {
                "family_key": key,
                "queries": [],
                "skills_sh": None,
                "skillsmp": None,
                "catalogs": [],
                "requires_source_review": True,
            },
        )
        query = str(record.get("query", ""))
        if query and query not in family["queries"]:
            family["queries"].append(query)
        source = record.get("source")
        if source == "skills.sh":
            current = family.get("skills_sh")
            if current is None or record.get("skills_sh_installs", 0) > current.get("skills_sh_installs", 0):
                family["skills_sh"] = record
        elif source == "skillsmp":
            current = family.get("skillsmp")
            if current is None or (record.get("repo_stars") or 0) > (current.get("repo_stars") or 0):
                family["skillsmp"] = record
        if source and source not in family["catalogs"]:
            family["catalogs"].append(source)

    def rank(item: dict[str, Any]) -> tuple[int, int, str]:
        skills_sh = item.get("skills_sh") or {}
        skillsmp = item.get("skillsmp") or {}
        return (
            -int(skills_sh.get("skills_sh_installs") or 0),
            -int(skillsmp.get("repo_stars") or 0),
            str(item["family_key"]),
        )

    output = list(families.values())
    for item in output:
        item["queries"].sort()
        item["catalogs"].sort()
    return sorted(output, key=rank)


def research(
    args: argparse.Namespace,
    skills_sh_runner: Callable[[str, float], list[dict[str, Any]]] = run_skills_sh,
    skillsmp_runner: Callable[[str, argparse.Namespace], list[dict[str, Any]]] = run_skillsmp,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    query_runs: list[dict[str, Any]] = []
    missing_evidence: list[str] = []
    for query in args.queries:
        run = {"query": query, "skills_sh": "not_run", "skillsmp": "not_run"}
        if not args.skip_skills_sh:
            try:
                found = skills_sh_runner(query, args.timeout)
                records.extend(found)
                run["skills_sh"] = "ok"
                run["skills_sh_candidates"] = len(found)
            except (RuntimeError, subprocess.TimeoutExpired) as exc:
                run["skills_sh"] = "error"
                run["skills_sh_error"] = str(exc)
                missing_evidence.append(f"skills.sh `{query}`: {exc}")
        if not args.skip_skillsmp:
            try:
                found = skillsmp_runner(query, args)
                records.extend(found)
                run["skillsmp"] = "ok"
                run["skillsmp_candidates"] = len(found)
            except RuntimeError as exc:
                run["skillsmp"] = "error"
                run["skillsmp_error"] = str(exc)
                missing_evidence.append(f"SkillsMP `{query}`: {exc}")
        query_runs.append(run)

    families = merge_candidates(records)
    complete = not missing_evidence and not args.skip_skills_sh and not args.skip_skillsmp
    ok = bool(families) and (complete or not args.strict)
    return {
        "ok": ok,
        "complete": complete,
        "researched_at": date.today().isoformat(),
        "queries": args.queries,
        "metric_semantics": {
            "skills_sh_installs": "ecosystem install telemetry; not ratings or correctness",
            "skillsmp_repo_stars": "GitHub repository stars; not installs, ratings, or skill-specific quality",
            "cross_catalog_score": "not calculated; metrics remain separate",
        },
        "query_runs": query_runs,
        "candidate_family_count": len(families),
        "candidates": families,
        "missing_evidence": missing_evidence,
        "next_steps": [
            "shortlist by job relevance and role coverage, not combined popularity",
            "open canonical GitHub source and inspect SKILL.md before adoption",
            "verify license, maintenance, permissions, security, duplication, and rating evidence",
            "write keep/adapt/reject/invent synthesis before authoring",
        ],
    }


def summary_view(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": result["ok"],
        "complete": result["complete"],
        "researched_at": result["researched_at"],
        "queries": result["queries"],
        "candidate_family_count": result["candidate_family_count"],
        "query_runs": result["query_runs"],
        "missing_evidence": result["missing_evidence"],
        "full_output": "written to --output" if result.get("_has_output") else "use --output to preserve candidates",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Research and normalize prior-art skills across two catalogs.")
    parser.add_argument("queries", nargs="+", help="One to four intent-shaped search queries.")
    parser.add_argument("--skillsmp-limit", type=int, default=10, choices=range(1, 51), metavar="1-50")
    parser.add_argument("--skillsmp-sort", choices=("stars", "recent"), default="stars")
    parser.add_argument("--category")
    parser.add_argument("--occupation")
    parser.add_argument("--language")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=2, choices=range(0, 6), metavar="0-5")
    parser.add_argument("--retry-backoff", type=float, default=0.5)
    parser.add_argument("--retry-jitter", type=float, default=0.2)
    parser.add_argument("--skip-skills-sh", action="store_true")
    parser.add_argument("--skip-skillsmp", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Fail unless both catalogs succeed for every query.")
    parser.add_argument("--summary", action="store_true", help="Print only run status; --output still receives full JSON.")
    parser.add_argument("--output", help="Optional JSON output path.")
    args = parser.parse_args()
    if len(args.queries) > 4:
        parser.error("use at most four intent-shaped queries per research run")
    if args.skip_skills_sh and args.skip_skillsmp:
        parser.error("cannot skip both catalogs")
    if args.retry_backoff < 0 or args.retry_jitter < 0:
        parser.error("retry delay values must be non-negative")
    return args


def main() -> None:
    args = parse_args()
    result = research(args)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result["_has_output"] = True
    rendered = summary_view(result) if args.summary else result
    print(json.dumps(rendered, ensure_ascii=False, indent=2))
    if not result["ok"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
