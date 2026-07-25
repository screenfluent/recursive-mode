# recursive-review-bundle (prompt template)

> Paste this into chat if your agent does not support custom slash commands.

## Usage Pattern

```text
Generate pass <NNNN> of review <review-id> for recursive run <run-id> and audited phase <phase>.
```

## Script

```bash
python3 "<SKILL_DIR>/scripts/recursive-review-bundle.py" \
  --repo-root . \
  --run-id "<run-id>" \
  --phase "03.5 Code Review" \
  --role code-reviewer \
  --review-id code-review \
  --pass 0001 \
  --artifact-path "/.recursive/run/<run-id>/03.5-code-review.md" \
  --upstream-artifact "/.recursive/run/<run-id>/00-requirements.md" \
  --upstream-artifact "/.recursive/run/<run-id>/02-to-be-plan.md" \
  --upstream-artifact "/.recursive/run/<run-id>/03-implementation-summary.md" \
  --audit-question "Which accepted requirements remain incomplete?" \
  --audit-question "Which changed files drift from the approved plan?"
```

```powershell
pwsh -NoProfile -File "<SKILL_DIR>/scripts/recursive-review-bundle.ps1" `
  -RepoRoot . `
  -RunId "<run-id>" `
  -Phase "03.5 Code Review" `
  -Role code-reviewer `
  -ReviewId code-review `
  -ReviewPass 0001 `
  -ArtifactPath "/.recursive/run/<run-id>/03.5-code-review.md" `
  -UpstreamArtifact "/.recursive/run/<run-id>/00-requirements.md","/.recursive/run/<run-id>/02-to-be-plan.md","/.recursive/run/<run-id>/03-implementation-summary.md" `
  -AuditQuestion "Which accepted requirements remain incomplete?","Which changed files drift from the approved plan?"
```

Repeat the relevant upstream, addendum, prior-evidence, control-document, code, evidence and audit-question options as needed. Supply a stable review ID explicitly; when it is omitted, the generator derives one from the phase and role. Add routing paths, CLI and model only when routed delegation applies. The generator discovers relevant addenda and matching recursive skill memory by default; disable addendum discovery only with `--no-auto-addenda` or `-NoAutoAddenda`.

## What It Writes

- One immutable bundle at `/.recursive/run/<run-id>/evidence/review-bundles/<phase-key>/<review-id>/<NNNN>.md`.
- The reviewed artifact hash, audit-payload hash, executable diff basis and current changed-file snapshot.
- The upstream artifacts, discovered addenda and memory, supplied control/code/evidence references, audit questions and routing context.
- The canonical ledger path at `/.recursive/run/<run-id>/evidence/reviews/<phase-key>/<review-id>/ledger.md`.
- The fixed review-output contract owned by `recursive-review`: `## Review Scope`, `## Findings` and `## Verdict`, with stable `F-*` records under `## Findings`.

The generator refuses a phase label or artifact path that does not match the audited-phase registry, a review ID reused under another phase, an invalid pass ID, a non-executable diff basis, a missing reviewed artifact, or an attempt to overwrite an existing bundle.

## Record the Bundle

Record the review ID, bundle path and hash, ledger path, and verified-pass pointers through the exact six-field `## Review Metadata` schema in the installed `recursive-mode` artifact template. Routing details belong in the generated bundle or delegated action record, not as replacement fields in `## Review Metadata`.

Regenerate after any change to the reviewed diff, artifact or evidence basis by incrementing the pass ID; immutable bundles are never overwritten. Load `recursive-review` before consuming the bundle, and use `recursive-subagent` with the installed `recursive-subagent-action` runtime when delegated work produces a structured action record.
