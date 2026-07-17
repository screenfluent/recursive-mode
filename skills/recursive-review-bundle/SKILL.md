---
name: recursive-review-bundle
description: 'Use when recursive-mode work needs a canonical delegated-review or audit handoff. Generates reproducible immutable per-pass review input bundles for every audited phase using the repo scripts.'
---

# recursive-review-bundle

Prepare the reproducible input snapshot for delegated review. The bundle is not a finding ledger and does not own repair or acceptance; `recursive-review` owns those behaviors.

Each immutable per-pass bundle binds one audited artifact snapshot to one ledger pass.

## Use the canonical scripts

- `./.recursive/scripts/recursive-review-bundle.py`
- `./.recursive/scripts/recursive-review-bundle.ps1`

Prefer Python when both are available. Use the PowerShell adapter for a PowerShell-oriented path.

## Inputs

Provide repo root, run ID, phase, reviewer role, reviewed artifact, exact upstream artifacts, relevant questions, and a stable review ID. Add code, evidence, control-plane, routing, and prior-evidence refs that affect the review. The generator discovers relevant addenda by default.

```bash
python3 ./.recursive/scripts/recursive-review-bundle.py \
  --repo-root . \
  --run-id "<run-id>" \
  --phase "02 TO-BE" \
  --role planner \
  --review-id plan-review \
  --pass 0001 \
  --artifact-path "/.recursive/run/<run-id>/02-to-be-plan.md" \
  --upstream-artifact "/.recursive/run/<run-id>/00-requirements.md" \
  --upstream-artifact "/.recursive/run/<run-id>/01-as-is.md" \
  --audit-question "Which accepted requirements are not planned?"
```

```powershell
pwsh -NoProfile -File ./.recursive/scripts/recursive-review-bundle.ps1 `
  -RepoRoot . `
  -RunId "<run-id>" `
  -Phase "02 TO-BE" `
  -Role planner `
  -ReviewId plan-review `
  -ReviewPass 0001 `
  -ArtifactPath "/.recursive/run/<run-id>/02-to-be-plan.md" `
  -UpstreamArtifact "/.recursive/run/<run-id>/00-requirements.md","/.recursive/run/<run-id>/01-as-is.md" `
  -AuditQuestion "Which accepted requirements are not planned?"
```

## Required review output

For every audited phase, the generator fixes the output contract; callers cannot replace it with prose. Review output uses exactly:

```markdown
## Review Scope

## Findings

## Verdict
```

Every technical issue is a stable `F-*` record under `## Findings`. New findings start open. A reviewer or repair agent cannot assign terminal dispositions. Load `recursive-review` and its finding protocol before consuming the bundle.

## Acceptance

- Record both `Review Bundle Path` and `Review Ledger Path` in every audited artifact.
- Regenerate after any change to the reviewed diff, artifact, or evidence basis.
- Require the reviewer to cite the bundle-grounded upstream artifacts, addenda, diff basis, changed files, and evidence.
- Treat the bundle as input evidence, never proof of review quality or repair acceptance.

When routing applies, reread the repo routing policy and discovery inventory immediately before dispatch and cite the resolved paths/model in the bundle or action record.
