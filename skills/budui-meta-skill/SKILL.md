---
name: budui-meta-skill
description: |
  Research, create, improve, migrate, evaluate, package, install-check, govern, and safely publish budui-flavored agent skills from workflows, prompts, transcripts, docs, SOPs, runbooks, scripts, or notes. Use for new or existing skills, prior-art synthesis, routing/trigger boundaries, trigger or output evals, Skill IR, release gates, README/Profile preparation, GitHub repository and pull-request publication, versioned Releases, clean npx installation, team reuse, and create-and-publish flows. The publication path is self-contained and forbids direct default-branch pushes. Exclude one-off summaries, translations, ordinary docs, non-skill package publishing, and tasks that explicitly should not become a skill.
metadata:
  author: Budui
  version: "2.8.1-budui.1"
  upstream_inspiration: yaojingang/yao-meta-skill; joeseesun/qiaomu-skill-publisher
---

# Budui Meta Skill

Build reusable Budui skill packages, not long prompts.

## Router Rules

- Route by frontmatter `description` first.
- Once selected, `budui-meta-skill` is the single authoring authority. Do not also invoke a generic `skill-creator` unless the user explicitly requests comparison or this skill is unavailable.
- Built-in prior-art discovery belongs to this skill. Do not install, load, or delegate to a separate discovery skill.
- Built-in GitHub publishing belongs to this skill. Do not require or invoke a separate publisher skill after this package is selected.
- Keep the package root `SKILL.md` to routing and the minimal workflow. Put judgment in `references/`, deterministic behavior in `scripts/`, regression cases in `evals/`, and evidence in `reports/`.
- A package has one discoverable root `SKILL.md`; embedded examples and fixtures use `SKILL.example.md` or `SKILL.fixture.md`.
- Do not turn one-off summaries, translations, explanations, or brainstorming into skills.
- Match the user's action: create/refactor/package requests may edit; audit/evaluate/diagnose-only requests remain read-only; publish only when explicitly requested.
- Default to concise Chinese-first `budui-` names with no more than three preferred hyphen parts.
- Add `Copyright (c) 不兑`, GitHub `https://github.com/chuopen/` unless another owner is requested.

## Modes

- `Scaffold`: exploratory or personal; minimum useful files.
- `Production`: team reuse; README, interface, trigger eval, output contract, and install evidence.
- `Library`: shared infrastructure; Production plus Skill IR, portability, trust, and review cadence.
- `Governed`: public or high-trust; Library plus permission, rollback, secret, release, and claim gates.

Choose proportionally with [Operating Modes](references/operating-modes.md), [Gate Selection](references/gate-selection.md), and [QA Ladder](references/qa-ladder.md).

## Built-In Prior-Art Discovery

Before a new skill or substantial redesign:

1. Derive 2–4 intent-shaped queries covering outcome, domain action, quality mechanism, and an adjacent synonym when useful.
2. Prefer the unified runner:

```bash
python3 scripts/research_prior_art.py "<query 1>" "<query 2>" --strict --summary --output reports/prior-art-candidates.json
```

Its underlying catalog calls remain:

```bash
npx --yes skills find "<query>"
python3 scripts/search_skillsmp.py "<query>" --limit 20 --sort stars
```

3. Keep metrics separate: skills.sh installs measure adoption; SkillsMP stars belong to the source repository; neither is a user rating or quality score.
4. Deduplicate by canonical GitHub repository and skill path. Collapse translations, mirrors, and obvious forks without adding metrics together.
5. Shortlist genuinely relevant popularity, trust, and complementary anchors. Inspect source `SKILL.md`, maintenance, license, permissions, security signals, and available rating evidence; never execute untrusted candidate code just to study it.
6. Synthesize `keep / adapt / reject / invent`. Map each adopted mechanism to the new package instead of collaging prose.
7. Preserve dated sources, metrics, failures, deduplication, lessons, rejections, and missing evidence in `reports/prior-art-research.md` for Production+ or materially researched work.

If a catalog fails, continue with the other sources, record `missing evidence`, and lower the claim. Full method: [Prior-Art Research](references/prior-art-research.md).

## Generalization Gate

Before promoting one failure into a core rule:

1. restate it as a domain-neutral behavior
2. classify it as core mechanism, optional adapter, or eval-only fixture
3. promote only safety/factual/permission invariants or behavior repeated across unrelated domains
4. keep one-off details in fixtures or specialist references
5. rerun the original and unrelated boundary cases

Prefer intent fidelity, source fidelity, and decision rules over an expanding topic encyclopedia.

## Budui Skill OS

1. `Intent`: recurring job, users, inputs, output, exclusions, standards, references.
2. `Skill IR`: platform-neutral meaning and evidence boundary.
3. `Package`: lean root instructions, interface, README, and earned resources.
4. `Eval`: trigger boundaries first; output/runtime/human eval when risk justifies it.
5. `Review`: package, context, trust, install, README, and public claims.
6. `Operate`: explicit feedback, failures, drift, and next-iteration proposals without raw private content.

## Compact Workflow

1. Decide whether the request deserves a reusable skill; otherwise answer directly and create no package.
2. Capture job, finished output, target users, inputs, exclusions, permissions, standards, existing assets, platforms, and publication intent.
3. Pass prior-art discovery or record why it is not applicable or missing evidence.
4. Pass the generalization gate for sample-driven core changes.
5. Choose the lightest valid mode.
6. Write the `description` early; run `evals/trigger_cases.json` before expanding structure.
7. Create only earned resources. Never create ceremonial directories or duplicate README/SKILL prose.
8. Export `reports/skill-ir.json` for Production+, public, or cross-platform packages.
9. Add output evals when correctness, safety, persuasion, or repeatability cannot be shown by trigger tests alone.
10. Keep mutations within the requested action boundary and preserve rollback for risky changes.
11. Validate package, unit tests, trigger behavior, context budget, secret/trust boundaries, and evidence claims.
12. Produce the creation handoff and clearly label missing evidence.
13. When publication is requested, read [Self-Contained Skill Publishing](references/publishing.md), then use the bundled publisher for feature branch → validation → PR → merge → release/install verification; never push directly to the default branch.

Core commands:

```bash
python3 scripts/validate_skill.py .
python3 scripts/export_skill_ir.py . --output reports/skill-ir.json
python3 scripts/trigger_eval.py . --cases evals/trigger_cases.json --output reports/trigger-eval.json
python3 scripts/release_check.py . --phase local --run-tests
python3 scripts/publish_skill.py /path/to/skill --dry-run
```

## Gate Ladder

- `Scaffold`: valid frontmatter, useful README hook, natural triggers, explicit exclusions.
- `Production`: Scaffold plus interface, trigger eval, output contract, troubleshooting, root isolation, and install verification.
- `Library`: Production plus Skill IR, portability, trust, review cadence, and evidence artifacts.
- `Governed`: Library plus permission/rollback boundary, secret scan, output or integrity-preserving human evidence, and public-claim guard.

Unavailable telemetry, provider runs, approval, install proof, or human review must remain `missing evidence`; planned work is not proof. See [Review And Release Gates](references/review-release-gates.md) and [Resource Boundary Spec](references/resource-boundaries.md).

## Output Contract

For package-producing requests, provide only what the selected mode earns:

1. working skill directory and trigger-aware root `SKILL.md`
2. aligned `agents/interface.yaml`
3. human-facing README for shared/public skills
4. trigger cases and generated trigger report for Production+
5. Skill IR, prior-art report, and creation handoff for Production+
6. optional references, scripts, output evals, reports, and manifest when they improve judgment, repeatability, or evidence
7. publish artifacts only when publishing was requested

The final creation handoff must name the **reference skills studied**, give **candidate-specific lessons**, explain deliberate rejections and original contributions, and label each highlight as **design advantage**, **validated advantage**, or **hypothesis**. Never claim global superiority without a fair comparison. Use [Creation Handoff](references/creation-handoff.md).

## Publish Flow

1. Treat README as a product page: value, install, natural examples, prerequisites, outputs, configuration, risks, and troubleshooting.
2. Audit without mutation when useful: `python3 scripts/publish_skill.py /path/to/skill --dry-run`.
3. Only after an explicit publish request, run `python3 scripts/publish_skill.py /path/to/skill`.
4. The bundled publisher prepares MIT LICENSE, README and Budui profile assets; resolves skill/repository identity; blocks secrets and reused release versions; creates or reuses a GitHub repository; and publishes only through a feature branch and PR.
5. Merge is blocked by conflicts, failed/pending checks or requested changes. Successful publication creates `vX.Y.Z`, verifies `npx skills add --list`, performs an isolated install, and runs the published release gate.
6. Do not report publication complete until the remote default version, GitHub Release, discovery and clean installation are verified.

Detailed CLI and safety decisions: [Self-Contained Skill Publishing](references/publishing.md). README method: [GitHub README Playbook](references/github-readme-playbook.md). Operation method: [SkillOps Loop](references/skillops-loop.md).

## Budui Defaults

- Prefer practical, concise, publishable Chinese output.
- Keep one creator authority and one root skill entrypoint.
- Preserve platform-neutral source plus minimal adapters.
- Public claims must match trigger, output, runtime, install, or human evidence actually present.
- Upstream ideas are adopted semantically with attribution, not mirrored wholesale.

## Reference Map

- Design: [Skill Engineering Method](references/skill-engineering-method.md), [Skill Archetypes](references/skill-archetypes.md), [Intent Dialogue](references/intent-dialogue.md), [Non-Skill Decision Tree](references/non-skill-decision-tree.md)
- Evidence: [Eval Playbook](references/eval-playbook.md), [Output Eval](references/output-eval-method.md), [Skill IR](references/skill-ir-method.md), [Governance](references/governance.md)
- Release: [Self-Contained Publishing](references/publishing.md), [Review And Release Gates](references/review-release-gates.md), [GitHub README](references/github-readme-playbook.md), [SkillOps](references/skillops-loop.md)


## Personal defaults — authoritative

- This is 不兑's personal meta skill. New skill names MUST use `budui-<function>`; author/owner defaults to `不兑 (budui)`. Never label newly generated work as authored by the upstream creator.
- Before generating or substantially changing a skill, clarify the recurring job, inputs, outputs and boundaries with the user. Ask only unresolved material questions, preferably one at a time, then summarize the agreed scope and wait for confirmation. Existing explicit answers and confirmation count; do not repeat questions already answered.
- Personal, low-impact tools use Scaffold by default: a concise SKILL.md and only necessary resources. Do not impose manifest, multi-platform interfaces, research reports or release machinery on small local tools. Briefly research useful existing approaches; record unavailable evidence honestly.
- Use fuller checks for account operations, external publishing, destructive actions or team reuse. Preserve secret checks, authorization boundaries and independent verification.
- Write concise, practical Chinese. Explain decisions plainly; avoid promotional claims and unnecessary terminology.
- GitHub personal owner preference is `chuopen`; verify the current authenticated identity and the project's remote before publishing. Never store credentials in a skill. Do not redirect existing project remotes automatically.
- New repository visibility must be explicit; ask when missing. A request to create a skill does not authorize publishing it.
- Do not insert upstream bios, X links, donation images or QR codes into generated skills. No personal marketing block is required. Use only the confirmed GitHub link https://github.com/chuopen/ when needed.
- Preserve original copyright and source attribution for reused code. The upstream source of this personal fork is https://github.com/joeseesun/qiaomu-meta-skill . Historical reports describe the original version and are not validation evidence for this fork.
- These personal defaults override inherited branding, workflow weight and automatic profile instructions elsewhere in this package.


## 不兑专属 Skill 仓库（优先于单技能发布默认值）

用户已指定所有个人 Skill 发布到 `chuopen/budui-skills`，展示名称“不兑的专属 Skills 仓库”，可见性公开。
当用户说“把这个 Skill 上传到 GitHub”时，默认更新该合集的 `skills/<skill-name>/`，不另建单技能仓库；普通业务项目不适用此默认值。
先读取仓库实际状态和目标子目录，保留其他技能；同名且身份不明确时才询问。使用临时 checkout 整合目标目录，经敏感信息扫描后通过分支和 PR 更新，回读合并提交，验证 `npx skills add chuopen/budui-skills --list` 可发现该技能。
单技能 publish_skill.py 不支持合集布局，禁止对该合集直接执行该发布器；采用 Git/gh 的等价分支、PR、检查、合并流程。仅在用户要求版本发布时创建 Release。
不必重复询问本合集的名称和公开选择；若账号、仓库或公开风险与已确认范围发生实质变化再确认。已明确上传的授权允许执行常规提交和推送。
