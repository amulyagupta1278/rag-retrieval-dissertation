#!/usr/bin/env python3
"""Freeze Phase 7 mechanical evaluation and blinded 26-answer owner audit package."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs/v2/phase7_generation_claude_top3_v2"
FULL = RUN / "full_v2"
OUT = RUN / "evaluation_v1"
AUDIT = ROOT / "audits/phase7_generation/v2/evaluation_v1"
QA = ROOT / "data/v2/pilot/qa/pilot-qa-v2-owner-approved-20260724-r5.jsonl"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def canonical(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical(obj) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(canonical(row) + "\n" for row in rows), encoding="utf-8")


def answer_path(record: dict) -> Path:
    return ROOT / record["validated_answer_path"]


def build() -> dict:
    evaluator = load_json(RUN / "evaluator_protocol.json")
    audit_ids = evaluator["owner_audit"]["blinded_request_ids"]
    if len(audit_ids) != 26 or len(set(audit_ids)) != 26:
        raise ValueError("Frozen owner audit must contain 26 unique IDs")

    plans = {row["blinded_request_id"]: row for row in load_jsonl(RUN / "sealed/request_plan.jsonl")}
    payloads = {row["blinded_request_id"]: row for row in load_jsonl(RUN / "blinded/request_payloads.jsonl")}
    coverage = {row["blinded_request_id"]: row for row in load_jsonl(FULL / "sealed/coverage_manifest.jsonl")}
    qa = {row["question_id"]: row for row in load_jsonl(QA)}
    if set(plans) != set(payloads) or set(plans) != set(coverage) or len(plans) != 170:
        raise ValueError("Phase 7 plan/payload/coverage mismatch")

    mechanical = []
    packages = []
    for blinded_id in sorted(plans):
        plan = plans[blinded_id]
        payload = payloads[blinded_id]
        cov = coverage[blinded_id]
        parsed_input = json.loads(payload["request"]["messages"][0]["content"])
        answer_doc = load_json(answer_path(cov))
        answer = answer_doc["answer"]
        supplied = {item["evidence_id"] for item in parsed_input["evidence"]}
        cited = answer["cited_evidence_ids"]
        inline = set(re.findall(r"\[(E\d{2})\]", answer["answer"]))
        schema_valid = all(key in answer for key in ("answer", "cited_evidence_ids", "abstained", "abstention_reason"))
        citation_ids_valid = set(cited).issubset(supplied)
        citation_coverage_valid = (
            (answer["abstained"] and not answer["answer"] and not cited)
            or (not answer["abstained"] and bool(cited) and set(cited).issubset(inline))
        )
        mechanical.append(
            {
                "blinded_request_id": blinded_id,
                "query_id": plan["query_id"],
                "schema_valid": schema_valid,
                "citation_ids_valid": citation_ids_valid,
                "citation_coverage_valid": citation_coverage_valid,
                "abstained": answer["abstained"],
                "cited_evidence_n": len(cited),
                "response_sha256": answer_doc["response_sha256"],
            }
        )
        if blinded_id in audit_ids:
            q = qa[plan["query_id"]]
            packages.append(
                {
                    "blinded_request_id": blinded_id,
                    "question": parsed_input["question"],
                    "reference_answer": q["reference_answer"],
                    "evidence": parsed_input["evidence"],
                    "generated_answer": answer["answer"],
                    "cited_evidence_ids": cited,
                    "abstained": answer["abstained"],
                    "abstention_reason": answer["abstention_reason"],
                    "correctness": None,
                    "faithfulness": None,
                    "completeness": None,
                    "citation_accuracy": None,
                    "unsupported_claim_severity": None,
                    "abstention_quality": None,
                    "owner_notes": "",
                }
            )

    packages.sort(key=lambda row: audit_ids.index(row["blinded_request_id"]))
    if [row["blinded_request_id"] for row in packages] != audit_ids:
        raise ValueError("Owner audit order differs from frozen protocol")
    if any(not row["schema_valid"] or not row["citation_ids_valid"] for row in mechanical):
        raise ValueError("Mechanical validity failure")

    operational = load_json(FULL / "operational_summary.json")
    summary = {
        "schema_version": 1,
        "status": "mechanical_complete_owner_quality_audit_pending",
        "record_n": 170,
        "schema_valid_n": sum(row["schema_valid"] for row in mechanical),
        "citation_ids_valid_n": sum(row["citation_ids_valid"] for row in mechanical),
        "citation_coverage_valid_n": sum(row["citation_coverage_valid"] for row in mechanical),
        "abstention_n": sum(row["abstained"] for row in mechanical),
        "abstention_rate": sum(row["abstained"] for row in mechanical) / 170,
        "generation_failure_n": 0,
        "model": operational["model"],
        "cumulative_cost_usd": operational["cumulative_observed_phase7_cost_usd"],
        "owner_audit_record_n": 26,
        "quality_labels_complete": False,
        "h5_executed": False,
        "h5_blocker": "26 owner quality records are blank by protocol",
    }

    write_jsonl(OUT / "mechanical_records.jsonl", mechanical)
    write_json(OUT / "mechanical_summary.json", summary)
    write_json(OUT / "owner_audit_package.json", {"schema_version": 1, "rows": packages})

    package_json = json.dumps(packages, ensure_ascii=False).replace("</", "<\\/")
    rubric = """
<ul><li>correctness, faithfulness, completeness, citation_accuracy, abstention_quality: 0=fail, 1=partial, 2=pass.</li>
<li>unsupported_claim_severity: 0=none, 1=minor, 2=major.</li><li>Score every dimension. Add notes for any 0/1 or unsupported claim.</li></ul>"""
    page = f"""<!doctype html><meta charset='utf-8'><title>Phase 7 Owner Audit</title>
<style>body{{font:16px system-ui;max-width:1100px;margin:auto;padding:20px}}.card{{border:1px solid #bbb;padding:16px;margin:20px 0}}pre{{white-space:pre-wrap;background:#f5f5f5;padding:10px}}label{{display:inline-block;margin:6px}}select,textarea{{font:inherit}}textarea{{width:100%;height:70px}}</style>
<h1>Phase 7 — 26-answer blinded owner audit</h1><p>System identity hidden. Judge answer against reference and supplied evidence.</p>{rubric}<div id='app'></div>
<button onclick='save()'>Export completed JSON</button><script>const rows={package_json};const dims=['correctness','faithfulness','completeness','citation_accuracy','unsupported_claim_severity','abstention_quality'];
const esc=s=>String(s??'').replace(/[&<>\"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]));
document.querySelector('#app').innerHTML=rows.map((r,i)=>`<div class=card><h2>${{i+1}}/26 — ${{r.blinded_request_id}}</h2><b>Question</b><p>${{esc(r.question)}}</p><b>Reference</b><p>${{esc(r.reference_answer)}}</p>${{r.evidence.map(e=>`<b>${{e.evidence_id}}</b><pre>${{esc(e.text)}}</pre>`).join('')}}<b>Generated answer</b><pre>${{esc(r.generated_answer||('[ABSTAINED] '+r.abstention_reason))}}</pre>${{dims.map(d=>`<label>${{d}} <select data-i=${{i}} data-d=${{d}}><option value=''>—</option><option>0</option><option>1</option><option>2</option></select></label>`).join('')}}<textarea data-note=${{i}} placeholder='Owner notes'></textarea></div>`).join('');
function save(){{document.querySelectorAll('select').forEach(x=>rows[+x.dataset.i][x.dataset.d]=x.value===''?null:+x.value);document.querySelectorAll('textarea').forEach(x=>rows[+x.dataset.note].owner_notes=x.value);if(rows.some(r=>dims.some(d=>r[d]===null))){{alert('Complete all 156 scores first');return}}const b=new Blob([JSON.stringify({{schema_version:1,rows}},null,2)],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='phase7_owner_audit_26_COMPLETED.json';a.click()}}</script>"""
    (OUT / "phase7_owner_audit_26.html").write_text(page, encoding="utf-8")

    artifacts = {
        str(path.relative_to(ROOT)): sha(path)
        for path in sorted([OUT / "mechanical_records.jsonl", OUT / "mechanical_summary.json", OUT / "owner_audit_package.json", OUT / "phase7_owner_audit_26.html"])
    }
    manifest = {
        "schema_version": 1,
        "status": "frozen_pending_owner_quality_audit",
        "base_generation_checkpoint_sha256": sha(ROOT / "audits/phase7_generation/v2/full_v2_success_checkpoint.json"),
        "evaluator_protocol_sha256": sha(RUN / "evaluator_protocol.json"),
        "artifacts": artifacts,
        "api_calls_n": 0,
        "ai_assigned_quality_labels_n": 0,
    }
    write_json(AUDIT / "freeze_manifest.json", manifest)
    return {"summary": summary, "manifest": manifest}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args()
    if not args.build:
        parser.error("use --build")
    print(json.dumps(build(), indent=2))


if __name__ == "__main__":
    main()
