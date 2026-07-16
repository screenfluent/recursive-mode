#!/usr/bin/env python3
"""
Generate a recursive-mode subagent action record scaffold.
"""

from __future__ import annotations

import argparse
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

import recursive_phase_rules as phase_rules
import recursive_review_action as review_action
import recursive_review_ledger as review_ledger_contract


FINDING_ID_RE = re.compile(r"F-[0-9]{3,}")
RUN_ID_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
CLAIMED_OUTCOMES = {"none", "fixed", "blocked"}
REVIEW_PROTOCOL_PATH = ".agents/skills/recursive-review/references/finding-protocol.md"
REVIEW_EXECUTION_TOKENS = {"review", "reviewer", "audit", "auditor", "repair", "repairer"}
REPAIR_EXECUTION_TOKENS = {"repair", "repairer"}


def is_phase_3_5(value: str) -> bool:
    return bool(re.match(r"^\s*(?:phase\s+)?0?3[.]5(?:[\s-]|$)", value, re.IGNORECASE))


def execution_mode_tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.lower()))


def normalize_repo_path(raw_path: str) -> str:
    return raw_path.replace("\\", "/").strip().lstrip("/")


def slugify(value: str) -> str:
    lowered = value.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug or "action"


def render_path_list(title: str, values: list[str]) -> list[str]:
    lines = [title]
    if not values:
        lines.append("- none")
        return lines
    lines.extend(f"- `{value}`" for value in values)
    return lines


def render_text_list(title: str, values: list[str]) -> list[str]:
    lines = [title]
    if not values:
        lines.append("- none")
        return lines
    lines.extend(f"- {value}" for value in values)
    return lines


def render_claim_values(title: str, values: list[str], *, paths: bool = False) -> list[str]:
    lines = [f"- {title}:"]
    if not values:
        lines.append("  - none")
        return lines
    for value in values:
        rendered = f"/{normalize_repo_path(value)}" if paths else value
        lines.append(f"  - `{rendered}`" if paths else f"  - {rendered}")
    return lines


def content_sha256(content: str) -> str:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def parse_finding_values(values: list[str], option_name: str) -> tuple[dict[str, list[str]], str | None]:
    parsed: dict[str, list[str]] = {}
    for raw in values:
        finding_id, separator, value = raw.partition("=")
        finding_id = finding_id.strip()
        value = value.strip()
        if not separator or not FINDING_ID_RE.fullmatch(finding_id) or int(finding_id.split("-", 1)[1]) == 0 or not value:
            return {}, f"{option_name} must use F-NNN=value."
        parsed.setdefault(finding_id, []).append(value)
    return parsed, None


def validate_finding_claims(
    claims: dict[str, list[str]],
    changes: dict[str, list[str]],
    verification: dict[str, list[str]],
) -> str | None:
    for finding_id, outcomes in claims.items():
        if len(outcomes) != 1:
            return f"{finding_id} must have exactly one claimed outcome."
        outcome = outcomes[0]
        if outcome not in CLAIMED_OUTCOMES:
            return f"{finding_id} claimed outcome must be one of: none, fixed, blocked."
        finding_changes = changes.get(finding_id, [])
        finding_verification = verification.get(finding_id, [])
        if outcome == "none" and (finding_changes or finding_verification):
            return f"{finding_id} with claimed outcome none cannot claim changes or verification."
        if outcome == "fixed" and (not finding_changes or not finding_verification):
            return f"{finding_id} with claimed outcome fixed requires changed paths and verification."
        if outcome == "blocked" and not finding_verification:
            return f"{finding_id} with claimed outcome blocked requires blocking evidence."
    unattached = (set(changes) | set(verification)) - set(claims)
    if unattached:
        return f"Finding claim data has no matching --finding-claim: {', '.join(sorted(unattached))}"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a recursive-mode subagent action record scaffold.")
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    parser.add_argument("--run-id", required=True, help="Run ID under .recursive/run/.")
    parser.add_argument("--subagent-id", required=True, help="Subagent identifier.")
    parser.add_argument("--phase", required=True, help="Phase name for the action record.")
    parser.add_argument("--purpose", required=True, help="Invocation purpose.")
    parser.add_argument("--execution-mode", required=True, help="Execution mode, e.g. review, audit, implementer.")
    parser.add_argument("--artifact-path", default="", help="Repo-relative current artifact path.")
    parser.add_argument("--upstream-artifact", action="append", default=[], help="Repo-relative upstream artifact path.")
    parser.add_argument("--addendum", action="append", default=[], help="Repo-relative addendum path.")
    parser.add_argument("--review-bundle", default="", help="Repo-relative review bundle path if used.")
    parser.add_argument("--diff-basis", default="", help="Explicit diff basis summary if not inferred.")
    parser.add_argument("--code-ref", action="append", default=[], help="Repo-relative code reference path.")
    parser.add_argument("--memory-ref", action="append", default=[], help="Repo-relative memory doc path.")
    parser.add_argument("--audit-question", action="append", default=[], help="Audit/task question passed to the subagent.")
    parser.add_argument("--action-taken", action="append", default=[], help="Concrete delegated action taken by the subagent.")
    parser.add_argument("--created-file", action="append", default=[], help="Repo-relative created file path.")
    parser.add_argument("--modified-file", action="append", default=[], help="Repo-relative modified file path.")
    parser.add_argument("--reviewed-file", action="append", default=[], help="Repo-relative reviewed file path.")
    parser.add_argument("--untouched-file", action="append", default=[], help="Repo-relative relevant but untouched file path.")
    parser.add_argument("--artifact-read", action="append", default=[], help="Repo-relative recursive artifact read by the subagent.")
    parser.add_argument("--artifact-updated", action="append", default=[], help="Repo-relative recursive artifact updated by the subagent.")
    parser.add_argument("--evidence-used", action="append", default=[], help="Repo-relative evidence path used by the subagent.")
    parser.add_argument("--finding", action="append", default=[], help="Free-form finding for non-audited action records only.")
    parser.add_argument("--review-ledger", default="", help="Canonical review ledger path for review/audit action records.")
    parser.add_argument("--finding-claim", action="append", default=[], help="Structured claim F-NNN=none|fixed|blocked. Repeat per finding.")
    parser.add_argument("--finding-change", action="append", default=[], help="Structured changed path F-NNN=path. Repeat as needed.")
    parser.add_argument("--finding-verification", action="append", default=[], help="Structured verification F-NNN=command-or-evidence. Repeat as needed.")
    parser.add_argument("--verification-path", action="append", default=[], help="Repo-relative file or artifact path the controller should inspect first.")
    parser.add_argument("--verification-item", action="append", default=[], help="Main-agent verification handoff item.")
    parser.add_argument("--router-used", default="", help="Router identifier used for delegated dispatch, e.g. recursive-router.")
    parser.add_argument("--routed-role", default="", help="Canonical routed role resolved for this action.")
    parser.add_argument("--routed-cli", default="", help="Resolved external CLI id if any.")
    parser.add_argument("--routed-model", default="", help="Resolved model id if any.")
    parser.add_argument("--routing-config-path", default="", help="Repo-relative routing policy path.")
    parser.add_argument("--routing-discovery-path", default="", help="Repo-relative routing discovery path.")
    parser.add_argument("--routing-resolution-basis", default="", help="Short explanation of how the route was resolved.")
    parser.add_argument("--routing-fallback-reason", default="", help="Why execution fell back from routed delegation, if applicable.")
    parser.add_argument("--cli-probe-summary", default="", help="Compact CLI probe summary for the action record.")
    parser.add_argument("--prompt-bundle-path", default="", help="Repo-relative routed prompt bundle path if used.")
    parser.add_argument("--invocation-exit-code", default="", help="External CLI invocation exit code if applicable.")
    parser.add_argument("--output-capture-path", action="append", default=[], help="Repo-relative captured output path from the routed CLI.")
    parser.add_argument("--output-name", default="", help="Optional action record filename under subagents/.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    run_id = args.run_id.strip()
    if not RUN_ID_RE.fullmatch(run_id):
        print("[FAIL] Run ID must be a canonical kebab-case directory name.")
        return 1
    run_root = repo_root / ".recursive" / "run"
    run_dir = run_root / run_id
    if run_dir.is_symlink() or run_dir.resolve().parent != run_root.resolve():
        print("[FAIL] Resolved run directory must remain directly beneath the repository run root.")
        return 1
    if not run_dir.exists():
        print(f"[FAIL] Run directory not found: {run_dir}")
        return 1

    review_ledger = normalize_repo_path(args.review_ledger) if args.review_ledger.strip() else ""
    bundle_path = normalize_repo_path(args.review_bundle) if args.review_bundle.strip() else ""
    finding_claims, claim_error = parse_finding_values(args.finding_claim, "--finding-claim")
    finding_changes, change_error = parse_finding_values(args.finding_change, "--finding-change")
    finding_verification, verification_error = parse_finding_values(args.finding_verification, "--finding-verification")
    structured_error = claim_error or change_error or verification_error
    if structured_error:
        print(f"[FAIL] {structured_error}")
        return 1
    structured_error = validate_finding_claims(finding_claims, finding_changes, finding_verification)
    if structured_error:
        print(f"[FAIL] {structured_error}")
        return 1
    structured_requested = bool(review_ledger or finding_claims or finding_changes or finding_verification)
    audited_phase_key = phase_rules.audited_phase_key_from_label(args.phase)
    if audited_phase_key is not None and args.finding:
        print("[FAIL] Audited phases cannot use unstructured --finding; findings require --review-ledger and canonical claims.")
        return 1
    execution_tokens = execution_mode_tokens(args.execution_mode)
    review_execution = bool(execution_tokens & REVIEW_EXECUTION_TOKENS)
    repair_execution = bool(execution_tokens & REPAIR_EXECUTION_TOKENS)
    lossless_action = audited_phase_key is not None and (review_execution or structured_requested)
    review_mode = is_phase_3_5(args.phase) or (audited_phase_key is not None and review_execution) or structured_requested
    if (structured_requested or review_mode) and not review_ledger:
        print("[FAIL] Review/audit action records require --review-ledger.")
        return 1
    if structured_requested and args.finding:
        print("[FAIL] Structured review claims cannot be combined with unstructured --finding.")
        return 1
    ledger_match = None
    if review_mode and review_ledger:
        expected_phase_key = audited_phase_key or ("phase-3-5" if is_phase_3_5(args.phase) else None)
        ledger_match = re.fullmatch(
            rf"[.]recursive/run/{re.escape(args.run_id.strip())}/evidence/reviews/{re.escape(expected_phase_key or 'invalid-phase')}/(?P<review_id>[a-z0-9]+(?:-[a-z0-9]+)*)/ledger[.]md",
            review_ledger,
        )
        if not ledger_match:
            print("[FAIL] Review Ledger must use the canonical active-run audited-phase evidence path.")
            return 1
    if review_ledger and not (repo_root / review_ledger).is_file():
        print(f"[FAIL] Review ledger not found: /{review_ledger}")
        return 1
    if lossless_action:
        if not bundle_path:
            print("[FAIL] Review/repair action records require --review-bundle.")
            return 1
        if repair_execution and not finding_claims:
            print("[FAIL] Repair action records require at least one --finding-claim.")
            return 1
        review_id = ledger_match.group("review_id") if ledger_match else "invalid-review"
        bundle_match = re.fullmatch(
            rf"[.]recursive/run/{re.escape(args.run_id.strip())}/evidence/review-bundles/{re.escape(audited_phase_key or 'invalid-phase')}/{re.escape(review_id)}/(?P<review_pass>[0-9]{{4}})[.]md",
            bundle_path,
        )
        if not bundle_match or int(bundle_match.group("review_pass")) == 0:
            print("[FAIL] Review Bundle must use the canonical active-run phase/review/pass path matching the Review Ledger.")
            return 1
        bundle_file = repo_root / bundle_path
        if not bundle_file.is_file() or bundle_file.is_symlink():
            print(f"[FAIL] Canonical immutable review bundle not found: /{bundle_path}")
            return 1
        ledger_result = review_ledger_contract.validate_ledger(repo_root, repo_root / review_ledger)
        if not ledger_result.valid or ledger_result.document is None:
            print("[FAIL] Review Ledger failed the shared lossless validator:")
            for issue in ledger_result.issues:
                print(f"- {issue}")
            return 1
        cited_bundle = ledger_result.document.scope.get("Reviewed Artifact", "")
        if cited_bundle != f"/{bundle_path}":
            print("[FAIL] Review Bundle must be the exact Reviewed Artifact bound by the validated ledger pass.")
            return 1
        claim_issues = review_action.validate_claim_ids(ledger_result.document, finding_claims)
        if claim_issues:
            for issue in claim_issues:
                print(f"[FAIL] {issue}")
            return 1

    subagents_dir = run_dir / "subagents"
    if subagents_dir.is_symlink():
        print("[FAIL] Subagent action directory cannot be a symlink.")
        return 1
    subagents_dir.mkdir(parents=True, exist_ok=True)
    if subagents_dir.resolve().parent != run_dir.resolve():
        print("[FAIL] Resolved subagent action directory must remain directly beneath the run directory.")
        return 1

    artifact_path = normalize_repo_path(args.artifact_path) if args.artifact_path.strip() else ""
    artifact_hash = ""
    if artifact_path and (repo_root / artifact_path).exists():
        artifact_hash = content_sha256((repo_root / artifact_path).read_text(encoding="utf-8"))

    diff_basis = args.diff_basis.strip() or "See /.recursive/run/<run-id>/00-worktree.md for the normalized diff basis used."
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    output_name = args.output_name.strip()
    if not output_name:
        output_name = f"{timestamp.replace(':', '').replace('-', '')}-{slugify(args.subagent_id)}-action.md"
    normalized_output_name = output_name.replace("\\", "/")
    if normalized_output_name in {".", ".."} or "/" in normalized_output_name or Path(normalized_output_name).name != normalized_output_name:
        print("[FAIL] Output name must be a single filename under the run subagents directory.")
        return 1
    output_name = normalized_output_name
    if not output_name.lower().endswith(".md"):
        output_name = f"{output_name}.md"
    output_path = (subagents_dir / output_name).resolve()
    if output_path.parent != subagents_dir.resolve():
        print("[FAIL] Resolved output path must remain directly beneath the run subagents directory.")
        return 1
    output_rel = normalize_repo_path(str(output_path.relative_to(repo_root)))

    upstream_artifacts = sorted(set(normalize_repo_path(value) for value in args.upstream_artifact if value.strip()))
    addenda = sorted(set(normalize_repo_path(value) for value in args.addendum if value.strip()))
    code_refs = sorted(set(normalize_repo_path(value) for value in args.code_ref if value.strip()))
    memory_refs = sorted(set(normalize_repo_path(value) for value in args.memory_ref if value.strip()))
    created_files = sorted(set(normalize_repo_path(value) for value in args.created_file if value.strip()))
    modified_files = sorted(set(normalize_repo_path(value) for value in args.modified_file if value.strip()))
    reviewed_files = sorted(set(normalize_repo_path(value) for value in args.reviewed_file if value.strip()))
    untouched_files = sorted(set(normalize_repo_path(value) for value in args.untouched_file if value.strip()))
    artifacts_read = sorted(set(normalize_repo_path(value) for value in args.artifact_read if value.strip()))
    artifacts_updated = sorted(set(normalize_repo_path(value) for value in args.artifact_updated if value.strip()))
    evidence_used = sorted(set(normalize_repo_path(value) for value in args.evidence_used if value.strip()))
    actions_taken = [value.strip() for value in args.action_taken if value.strip()]
    verification_paths = sorted(set(normalize_repo_path(value) for value in args.verification_path if value.strip()))
    output_capture_paths = sorted(set(normalize_repo_path(value) for value in args.output_capture_path if value.strip()))
    routing_config_path = normalize_repo_path(args.routing_config_path) if args.routing_config_path.strip() else ""
    routing_discovery_path = normalize_repo_path(args.routing_discovery_path) if args.routing_discovery_path.strip() else ""
    prompt_bundle_path = normalize_repo_path(args.prompt_bundle_path) if args.prompt_bundle_path.strip() else ""

    lines: list[str] = [
        "# Subagent Action Record",
        "",
        "## Metadata",
        f"- Subagent ID: `{args.subagent_id.strip()}`",
        f"- Run ID: `{args.run_id.strip()}`",
        f"- Phase: `{args.phase.strip()}`",
        f"- Purpose: `{args.purpose.strip()}`",
        f"- Execution Mode: `{args.execution_mode.strip()}`",
        f"- Timestamp: `{timestamp}`",
        f"- Action Record Path: `/{output_rel}`",
        "",
        "## Inputs Provided",
        f"- Current Artifact: `{('/' + artifact_path) if artifact_path else 'none'}`",
        f"- Artifact Content Hash: `{artifact_hash or 'UNKNOWN'}`",
    ]
    lines.extend(render_path_list("- Upstream Artifacts:", [f"/{value}" for value in upstream_artifacts]))
    lines.extend(render_path_list("- Addenda:", [f"/{value}" for value in addenda]))
    lines.append(f"- Review Bundle: `{('/' + bundle_path) if bundle_path else 'none'}`")
    lines.append(f"- Diff Basis: `{diff_basis}`")
    lines.extend(render_path_list("- Code Refs:", [f"/{value}" for value in code_refs]))
    lines.extend(render_path_list("- Memory Refs:", [f"/{value}" for value in memory_refs]))
    lines.extend(render_text_list("- Audit / Task Questions:", args.audit_question))
    lines.append("")
    lines.append("## Routing")
    lines.append(f"- Router Used: `{args.router_used.strip() or 'none'}`")
    lines.append(f"- Routed Role: `{args.routed_role.strip() or 'none'}`")
    lines.append(f"- Routed CLI: `{args.routed_cli.strip() or 'none'}`")
    lines.append(f"- Routed Model: `{args.routed_model.strip() or 'none'}`")
    lines.append(f"- Routing Config Path: `{('/' + routing_config_path) if routing_config_path else 'none'}`")
    lines.append(f"- Routing Discovery Path: `{('/' + routing_discovery_path) if routing_discovery_path else 'none'}`")
    lines.append(f"- Routing Resolution Basis: `{args.routing_resolution_basis.strip() or 'none'}`")
    lines.append(f"- Routing Fallback Reason: `{args.routing_fallback_reason.strip() or 'none'}`")
    lines.append(f"- CLI Probe Summary: `{args.cli_probe_summary.strip() or 'none'}`")
    lines.append(f"- Prompt Bundle Path: `{('/' + prompt_bundle_path) if prompt_bundle_path else 'none'}`")
    lines.append(f"- Invocation Exit Code: `{args.invocation_exit_code.strip() or 'none'}`")
    lines.extend(render_path_list("- Output Capture Paths:", [f"/{value}" for value in output_capture_paths]))
    lines.append("")
    lines.extend(render_text_list("## Claimed Actions Taken", actions_taken))
    lines.append("")
    lines.append("## Claimed File Impact")
    lines.extend(render_path_list("### Created", [f"/{value}" for value in created_files]))
    lines.extend(render_path_list("### Modified", [f"/{value}" for value in modified_files]))
    lines.extend(render_path_list("### Reviewed", [f"/{value}" for value in reviewed_files]))
    lines.extend(render_path_list("### Relevant but Untouched", [f"/{value}" for value in untouched_files]))
    lines.append("")
    lines.append("## Claimed Artifact Impact")
    lines.extend(render_path_list("### Read", [f"/{value}" for value in artifacts_read]))
    lines.extend(render_path_list("### Updated", [f"/{value}" for value in artifacts_updated]))
    lines.extend(render_path_list("### Evidence Used", [f"/{value}" for value in evidence_used]))
    lines.append("")
    if structured_requested or review_mode:
        lines.append("## Claimed Findings")
        lines.append(f"- Review Protocol: `/{REVIEW_PROTOCOL_PATH}`")
        if lossless_action:
            lines.append(f"- Review Bundle: `/{bundle_path}`")
        lines.append(f"- Review Ledger: `/{review_ledger}`")
        if lossless_action:
            lines.append(f"- Review Pass: `{bundle_match.group('review_pass')}`")
        if not finding_claims:
            lines.append("- Claims: none")
        for finding_id in sorted(finding_claims, key=lambda value: int(value.split("-", 1)[1])):
            outcome = finding_claims[finding_id][0]
            lines.append("")
            lines.append(f"### {finding_id}")
            lines.append(f"- Claimed outcome: `{outcome}`")
            lines.extend(render_claim_values("Claimed changes", finding_changes.get(finding_id, []), paths=True))
            lines.extend(render_claim_values("Claimed verification", finding_verification.get(finding_id, [])))
        lines.append("")
    else:
        lines.extend(render_text_list("## Claimed Findings", args.finding))
        lines.append("")
    lines.append("## Verification Handoff")
    lines.extend(render_path_list("- Inspect first:", [f"/{value}" if value.startswith(".recursive/") else value for value in verification_paths]))
    lines.extend(render_text_list("- Notes:", args.verification_item))
    lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"[OK] Wrote subagent action record: /{output_rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
