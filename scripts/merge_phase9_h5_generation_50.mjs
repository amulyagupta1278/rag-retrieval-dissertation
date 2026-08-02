#!/usr/bin/env node
import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const root = process.cwd();
const input = "/Users/amulyagupta/Downloads/phase9_h5_claim_review_150_100of150_COMPLETED.xlsx";
const outDir = path.join(root, "outputs/phase9_h5");
const outPath = path.join(outDir, "phase9_h5_claim_review_150_READY_FOR_REVIEW.xlsx");
const freeze = path.join(root, "runs/phase9_h5_followup/generation_freeze");
const generated = path.join(root, "runs/phase9_h5_followup/generation_50/validated");
const qaPath = path.join(root, "runs/phase8_r4_improvements/benchmark/qa_dev_test.jsonl");
const chunksPath = path.join(root, "runs/phase8_r4_improvements/corpus/chunks_section_aware_450w.jsonl");

const jsonl = async p => (await fs.readFile(p, "utf8")).trim().split(/\n/).filter(Boolean).map(JSON.parse);
const plans = (await jsonl(path.join(freeze, "request_plan.jsonl"))).sort((a,b) => a.blinded_request_id.localeCompare(b.blinded_request_id));
if (plans.length !== 50) throw new Error(`expected 50 plans, found ${plans.length}`);
const qa = Object.fromEntries((await jsonl(qaPath)).map(row => [row.question_id, row]));
const chunks = Object.fromEntries((await jsonl(chunksPath)).map(row => [row.chunk_id, row.text]));
const rows = [];
for (let i = 0; i < plans.length; i++) {
  const plan = plans[i];
  const valid = JSON.parse(await fs.readFile(path.join(generated, `${plan.blinded_request_id}.json`), "utf8"));
  const answer = valid.answer;
  rows.push([
    `H5A${String(i + 101).padStart(3, "0")}`, "READY_FROZEN", plan.blinded_request_id,
    qa[plan.query_id].question, qa[plan.query_id].reference_answer,
    chunks[plan.evidence_id_to_chunk_id.E01] ?? "", chunks[plan.evidence_id_to_chunk_id.E02] ?? "", chunks[plan.evidence_id_to_chunk_id.E03] ?? "",
    answer.answer, answer.abstained, answer.abstention_reason, answer.cited_evidence_ids.join(" | "),
  ]);
}

const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(input));
for (const [name, reviewer] of [["Reviewer A", "REVIEWER_A"], ["Reviewer B", "REVIEWER_B"]]) {
  const sheet = wb.worksheets.getItem(name);
  sheet.getRange("B2:B101").values = Array.from({length:100}, () => ["READY_FROZEN"]);
  sheet.getRange("A102:L151").values = rows;
  sheet.getRange("M102:M151").values = Array.from({length:50}, () => [reviewer]);
  sheet.getRange("N102:R151").values = Array.from({length:50}, () => [null,null,null,null,null]);
  sheet.getRange("U102:U151").values = Array.from({length:50}, () => ["NOT_STARTED"]);
  sheet.getRange("V102:V151").values = Array.from({length:50}, () => [""]);
}
const adj = wb.worksheets.getItem("Adjudication");
adj.getRange("B2:B101").values = Array.from({length:100}, () => ["READY_FROZEN"]);
adj.getRange("A102:C151").values = rows.map(row => row.slice(0,3));
adj.getRange("H102:L151").values = Array.from({length:50}, () => [null,null,null,null,null]);
adj.getRange("N102:P151").values = Array.from({length:50}, () => ["", "PENDING", ""]);
const instructions = wb.worksheets.getItem("Instructions");
instructions.getRange("A1").values = [["H5 Claim-Level Faithfulness Review — 150 Answers"]];
instructions.getRange("B3").values = [["READY FOR REVIEW — all 150 protected answer/evidence rows populated and frozen. Rows 101–150 require Reviewer A and Reviewer B scoring."]];

await fs.mkdir(outDir, {recursive:true});
for (const [sheetName, range, name] of [["Instructions","A1:B12","ready_instructions"],["Reviewer A","A98:V106","ready_reviewer_a"],["Reviewer B","A98:V106","ready_reviewer_b"],["Adjudication","A98:P106","ready_adjudication"]]) {
  const preview = await wb.render({sheetName, range, scale:0.9, format:"png"});
  await fs.writeFile(path.join(outDir, `${name}.png`), new Uint8Array(await preview.arrayBuffer()));
}
const errors = await wb.inspect({kind:"match", searchTerm:"#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options:{useRegex:true,maxResults:300}, summary:"final formula error scan"});
await fs.writeFile(path.join(outDir, "ready_formula_errors.ndjson"), errors.ndjson);
const output = await SpreadsheetFile.exportXlsx(wb);
await output.save(outPath);
const digest = crypto.createHash("sha256").update(await fs.readFile(outPath)).digest("hex");
await fs.writeFile(path.join(outDir, "phase9_h5_ready_manifest.json"), JSON.stringify({status:"ready_for_two_reviewer_scoring", answer_n:150, newly_generated_n:50, workbook_sha256:digest}, null, 2) + "\n");
console.log(JSON.stringify({outPath, workbook_sha256:digest}, null, 2));
