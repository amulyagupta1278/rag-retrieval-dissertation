import csv,json
from pathlib import Path
FORBIDDEN={'system','systems','rank','score','current_gold','gold','relevance','predicted_relevance','contributions','contributing_systems'}
def test_phase2b_blind_package_has_no_provenance_leakage():
 root=Path(__file__).parents[1]; rows=list(csv.DictReader((root/'audits/phase2b/owner_judgments.csv').open()))
 assert len(rows)==504 and not (set(rows[0])&FORBIDDEN)
 assert all(not x['owner_grade_2_1_0_U'] and not x['owner_rationale'] for x in rows)
 sealed=[json.loads(x) for x in (root/'runs/v2/phase2a_r5_windowed/pool/sealed_provenance.jsonl').read_text().splitlines()]
 assert len(sealed)==504 and 'contributions' in sealed[0] and 'current_gold' in sealed[0]
def test_qc_sample_is_seeded_fifteen_percent():
 root=Path(__file__).parents[1]; qc=json.loads((root/'audits/phase2b/qc_rejudge_selection_sealed.json').read_text())
 assert qc['seed']==42 and qc['population']==504 and qc['sample_size']==76
