# Phase 7 Answer-Evaluation Rubric — Draft

Status: `draft_pending_owner_evaluator_selection`

Evaluation package must blind system identity, randomize display IDs, preserve one
answer per query/system pair, and separate scoring from sealed provenance.

## Dimensions and anchors

### Correctness (0–2)

- 2: all material factual content agrees with reference answer;
- 1: partly correct but contains a material omission or minor error;
- 0: materially wrong, unsupported, or nonresponsive.

### Faithfulness (0–2)

- 2: every material claim is supported by retrieved evidence;
- 1: main answer is supported but one limited claim lacks support;
- 0: material claims contradict or exceed supplied evidence.

### Completeness (0–2)

- 2: covers all required answer components;
- 1: covers some but misses at least one required component;
- 0: misses core answer requirements.

### Citation accuracy (0–2)

- 2: every citation supports associated claim;
- 1: mixed support or imprecise placement;
- 0: cited evidence does not support claims or citations are invalid.

### Unsupported claims

Record count plus severity: none, minor, material, or critical. Fluency never earns
credit for unsupported content.

### Abstention quality (0–2)

- 2: abstains when evidence is insufficient, or answers when sufficient;
- 1: partly appropriate but explanation or scope is weak;
- 0: unnecessary abstention or confident answer despite insufficient evidence.

## Evaluator options

Human-only maximizes direct human control but requires largest workload and repeat
sample. LLM judge requires exact provider/model/prompt/cost freeze, raw outputs,
failure preservation, and human audit. Hybrid routes disagreements, low-confidence
cases, unsupported claims, and abstentions to blinded human review. No option is
selected.

Each option must preregister randomization, repeat sample, agreement statistic,
adjudication, missing-output treatment, and evaluator failures before answers are
inspected.

