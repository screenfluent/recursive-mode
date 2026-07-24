# recursive-subagent-action (prompt template)

> Paste this into chat if your agent does not support custom slash commands.

## Usage Pattern

```text
Record delegated work for run <run-id>, binding every review claim to its canonical ledger and immutable bundle.
```

## Audited Repair Example

```bash
python3 "<SKILL_DIR>/scripts/recursive-subagent-action.py" \
  --repo-root . \
  --run-id "<run-id>" \
  --subagent-id repairer-01 \
  --phase "02 TO-BE" \
  --purpose "Repair plan review findings" \
  --execution-mode repair \
  --artifact-path "/.recursive/run/<run-id>/evidence/review-bundles/phase-2/plan-review/0001.md" \
  --review-bundle "/.recursive/run/<run-id>/evidence/review-bundles/phase-2/plan-review/0001.md" \
  --review-ledger "/.recursive/run/<run-id>/evidence/reviews/phase-2/plan-review/ledger.md" \
  --action-taken "Repaired the implementation and verification surfaces named by F-001." \
  --modified-file "src/app.py" \
  --finding-claim "F-001=fixed" \
  --finding-change "F-001=src/app.py" \
  --finding-verification "F-001=python3 -m unittest tests.test_app" \
  --verification-path "src/app.py" \
  --verification-item "Verify F-001 against the real diff and rerun the named test." \
  --output-name "plan-review-repair.md"
```

```powershell
pwsh -NoProfile -File "<SKILL_DIR>/scripts/recursive-subagent-action.ps1" `
  -RepoRoot . `
  -RunId "<run-id>" `
  -SubagentId repairer-01 `
  -Phase "02 TO-BE" `
  -Purpose "Repair plan review findings" `
  -ExecutionMode repair `
  -ArtifactPath "/.recursive/run/<run-id>/evidence/review-bundles/phase-2/plan-review/0001.md" `
  -ReviewBundle "/.recursive/run/<run-id>/evidence/review-bundles/phase-2/plan-review/0001.md" `
  -ReviewLedger "/.recursive/run/<run-id>/evidence/reviews/phase-2/plan-review/ledger.md" `
  -ActionTaken "Repaired the implementation and verification surfaces named by F-001." `
  -ModifiedFile "src/app.py" `
  -FindingClaim "F-001=fixed" `
  -FindingChange "F-001=src/app.py" `
  -FindingVerification "F-001=python3 -m unittest tests.test_app" `
  -VerificationPath "src/app.py" `
  -VerificationItem "Verify F-001 against the real diff and rerun the named test." `
  -OutputName "plan-review-repair.md"
```

Repeat file, artifact, evidence, question, action, verification and routing options as needed. Omit `--output-name` or `-OutputName` to use the timestamped subagent filename; an explicit output name must be a single filename under the run's `subagents/` directory.

## Review and Repair Claims

- Every audited review, audit or repair record cites the canonical review ledger and its exact immutable phase/review/pass bundle.
- The cited bundle must snapshot the current reviewed surface; refresh the pass and bundle after any changed diff byte, artifact or evidence basis before writing or relying on the action record.
- Use only `F-NNN=none|fixed|blocked` claims for findings that exist and remain open in the validated ledger. `fixed` requires concrete changed paths and reproducible verification; `blocked` requires blocking evidence; `none` carries neither changes nor verification.
- A repair record requires at least one structured claim. Free-form `--finding` or `-Finding` is reserved for non-audited action records.
- The action record contains claims only. It never assigns `Disposition`, writes controller verification or declares PASS.

## What It Writes

- One Markdown action record under `/.recursive/run/<run-id>/subagents/`.
- Invocation metadata, inputs, routing details, claimed actions, file and artifact impact, evidence, structured finding claims and the verification handoff.
- The current artifact content hash when that artifact exists. Prefer the stable reviewed bundle for audited work; refresh the record if any mutable referenced artifact changes.

The runtime rejects malformed or cross-ledger claims, missing, stale or mismatched ledgers and bundles, terminal finding IDs, incomplete fixed/blocked claims, unsafe run/output paths, symlinked `subagents/` directories or review bundles and audited free-form findings. A generated action record is evidence for controller inspection, never acceptance by itself.
