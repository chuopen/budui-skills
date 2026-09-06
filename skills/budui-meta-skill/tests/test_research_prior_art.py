#!/usr/bin/env python3
"""Tests for dual-catalog prior-art orchestration."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("research_prior_art", ROOT / "scripts" / "research_prior_art.py")
if SPEC is None or SPEC.loader is None:  # pragma: no cover
    raise RuntimeError("unable to load research_prior_art.py")
RESEARCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RESEARCH)


def args(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "queries": ["seo audit"],
        "timeout": 1.0,
        "skip_skills_sh": False,
        "skip_skillsmp": False,
        "strict": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class ResearchPriorArtTest(unittest.TestCase):
    def test_skills_sh_parser_handles_ansi_and_compact_installs(self) -> None:
        output = "\x1b[32mowner/repo@seo-audit\x1b[0m \x1b[36m177.3K installs\x1b[0m"
        result = RESEARCH.parse_skills_sh_output(output, "seo audit")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["skills_sh_installs"], 177300)
        self.assertEqual(result[0]["family_key"], "owner/repo:seo-audit")

    def test_cross_catalog_family_keeps_metrics_separate(self) -> None:
        merged = RESEARCH.merge_candidates(
            [
                {
                    "source": "skills.sh",
                    "query": "seo",
                    "family_key": "owner/repo:seo",
                    "skills_sh_installs": 100,
                },
                {
                    "source": "skillsmp",
                    "query": "seo audit",
                    "family_key": "owner/repo:seo",
                    "repo_stars": 900,
                },
            ]
        )
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["skills_sh"]["skills_sh_installs"], 100)
        self.assertEqual(merged[0]["skillsmp"]["repo_stars"], 900)
        self.assertNotIn("score", merged[0])

    def test_one_catalog_failure_degrades_with_missing_evidence(self) -> None:
        def skills_sh(_query: str, _timeout: float) -> list[dict[str, object]]:
            return [{"source": "skills.sh", "query": "seo", "family_key": "owner/repo:seo", "skills_sh_installs": 10}]

        def skillsmp(_query: str, _args: object) -> list[dict[str, object]]:
            raise RuntimeError("rate limited")

        result = RESEARCH.research(args(), skills_sh, skillsmp)
        self.assertTrue(result["ok"], result)
        self.assertFalse(result["complete"])
        self.assertTrue(result["missing_evidence"])

    def test_strict_mode_fails_on_partial_catalog_evidence(self) -> None:
        def skills_sh(_query: str, _timeout: float) -> list[dict[str, object]]:
            return [{"source": "skills.sh", "query": "seo", "family_key": "owner/repo:seo", "skills_sh_installs": 10}]

        def skillsmp(_query: str, _args: object) -> list[dict[str, object]]:
            raise RuntimeError("rate limited")

        result = RESEARCH.research(args(strict=True), skills_sh, skillsmp)
        self.assertFalse(result["ok"])

    def test_summary_omits_candidate_payload(self) -> None:
        result = {
            "ok": True,
            "complete": True,
            "researched_at": "2026-08-03",
            "queries": ["seo"],
            "candidate_family_count": 1,
            "query_runs": [],
            "missing_evidence": [],
            "candidates": [{"large": "payload"}],
        }
        summary = RESEARCH.summary_view(result)
        self.assertNotIn("candidates", summary)
        self.assertEqual(summary["candidate_family_count"], 1)


if __name__ == "__main__":
    unittest.main()
