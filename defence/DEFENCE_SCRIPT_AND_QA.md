# Defence script and Q&A preparation

Amulya Gupta · 2024AB05200
Target: 15 minutes of talk, 3 minutes of live demo, then questions.

---

## What went wrong last time, in one line

The deck never said what the documents were. The words *government*, *policy*, *citizen*,
*welfare*, *scheme* and *India* appeared **zero times** across all 13 slides. The evaluator
watched a talk about comparing five retrievers on an unnamed corpus, so "why did you do
this" was the correct question to ask.

The motivation was always in the written dissertation (§1.1). It just never reached the
slides. That is what this revision fixes.

---

## Before you walk in

- [ ] `defence/retrieval_evidence_demo.html` open in a browser tab, already loaded
- [ ] Deck in presenter view so you can see the speaker notes
- [ ] `python scripts/verify_headline_numbers.py` run once — if he asks whether the numbers
      are real, run it in front of him
- [ ] `START_HERE.md` open in a second tab in case he wants to look at the repository

---

## Opening — say this almost verbatim

> Last time I opened with the method. I want to start somewhere else, because the technical
> result only means something in context.
>
> Government departments and citizen helpdesks are deploying RAG assistants over welfare
> scheme guidelines. Someone asks whether they qualify for housing support. The system
> retrieves a document, and the language model answers from it — fluently, with citations,
> and completely confidently.
>
> If retrieval hands over the rural housing scheme when the person lives in a city, the
> answer is wrong. Not badly worded. Wrong. And the citizen has no way to tell.
>
> The generator cannot repair evidence it never received. That is why this dissertation
> evaluates retrieval and not generation.

Then move to slide 2.

---

## Timing

| Slides | Content | Time |
|---|---|---|
| 1–2 | Title, the problem | 1:30 |
| 3–4 | Why policy text is hard, the gap in the literature | 1:30 |
| 5–7 | Research question, benchmark, method | 2:30 |
| 8–9 | Headline finding, category breakdown | 2:30 |
| 10 | Worked example → **switch to demo** | 3:00 |
| 11–12 | Mechanism, cost | 1:30 |
| 13–14 | Hypotheses, generalisation | 2:00 |
| 15–16 | Contribution, limits | 1:30 |

If you are running long, cut slide 7 (method) and slide 11 (mechanism). Never cut slides
2, 4, 9 or 10 — those are the ones that answer his original objection.

---

## The three sentences that matter most

Land these clearly and pause after each.

1. **Slide 2** — "The generator cannot repair evidence it never received."
2. **Slide 4** — "Nobody actually knew. The assumption had never been tested here."
3. **Slide 13** — "A preregistered study that confirms everything it predicted has usually
   not been preregistered."

---

## The demo — slide 10

Have it already open on question v2q-018, which is where it loads by default.

Say:

> This is one of the 34 questions. It asks which scheme helps city households in lower and
> middle income bands get permanent homes. The answer is PMAY-Urban.
>
> BM25 put the correct passage at rank 1. The dense retriever put it at rank 5 — four wrong
> schemes above it. The entity graph never returned it at all, because the question contains
> no scheme name for its entity linker to anchor to.

Click a green row, read the passage aloud. Then click FAISS's rank-1 result and read what it
returned instead.

Then hand him the controls:

> Pick any question you like.

Let him drive. This is the single most persuasive thing in the whole defence — he can audit
the claim himself rather than take your word for it.

---

# Anticipated questions

Ordered by how likely they are.

### "Why does this need to be a dissertation? Why not just build the system?"

This is his original objection. Answer directly.

> Because building a system would not have told anyone which retriever to use. The field's
> confidence that dense embeddings beat lexical retrieval comes from MS MARCO and Natural
> Questions — open-domain web text, hundreds of thousands of queries, heavy paraphrase. A
> government policy corpus has the opposite statistical properties: 22 documents, bounded
> vocabulary, terminology fixed by statute, scheme names repeating verbatim.
>
> Transferring the conclusion across that gap is an assumption, and it had never been
> tested. So I built the benchmark that lets it be tested, and tested it. The answer turned
> out to contradict the assumption.

### "Only 34 questions. Is that enough to conclude anything?"

Concede immediately and precisely — do not get defensive.

> No, and I do not claim it is. Every paired confidence interval crosses zero and I say so
> on slide 14. What I claim is narrower: a consistent directional finding that reproduces on
> an independently acquired holdout with configurations frozen beforehand, together with a
> mechanism that explains it.
>
> The 34 questions are human-graded with a blind regrade and adjudicated disagreements. I
> would rather have 34 questions I can defend than 3,400 I cannot. And the benchmark is
> released, so the sample size question is now answerable by anyone, including you.

### "Isn't 'BM25 beats embeddings' already known?"

> It is known as an occasional finding on specific benchmarks, usually reported as an
> anomaly. Two things here are different. First, the domain — I have not found a controlled,
> human-judged evaluation on Indian government policy documentation. Second, the location of
> the effect: the gap is widest on paraphrase queries, which is precisely where the
> literature predicts lexical retrieval should collapse. That is not a restatement of a known
> result; it is a contradiction of the mechanism usually given for it.

### "Your paraphrase questions still contain document terminology. Doesn't that invalidate H2?"

He may well spot this — it is in your own Phase 8 verdicts. **Volunteer it before he does.**

> Yes, and I flagged it myself in the Phase 8 verdicts. Some rewritten questions retained
> content words that appear in the source, which weakens the intended lexical-mismatch test.
> That is a construct validity limitation and it is why I describe H2 as "not supported in
> this benchmark" rather than "semantic retrieval does not work."
>
> A paraphrase-only follow-up with adversarial rewrites is preregistered. What the current
> data does show is that on realistic policy questions — which is what a citizen actually
> types — lexical retrieval was not the weak point.

### "Four of five hypotheses failed. What did you actually establish?"

> Three things. A reusable benchmark that did not exist before. A measured result that runs
> against the field's default assumption, with the mechanism identified. And a cost-aware
> recommendation: for a citizen-facing policy assistant, BM25 or BM25 with fusion is the
> defensible default, and LLM reranking has to justify roughly 18 seconds per query against
> a gain of 0.037 MRR.
>
> The hypotheses were registered before evaluation precisely so I could not quietly rewrite
> them afterwards. Reporting that four were wrong is the protocol working.

### "Why is BM25 so much better on paraphrase? That seems backwards."

> Because the rewrites removed the scheme name but kept the rare content words — "cooking",
> "income", "housing". BM25 weights rare terms heavily, and in this corpus the rare terms are
> the discriminative ones. The embedding compresses the whole passage into one vector, and in
> a corpus where every housing document looks alike, that spreads probability across
> thematically similar but incorrect schemes. You can see it happening in the demo on v2q-018.

### "Why did the entity graph score zero on paraphrase?"

> Because it is NER-dependent. With no named entity in the query, the linker has no entry
> point into the graph at all. That is a structural property of entity-anchored retrieval on
> this domain, not a tuning failure — and it is a useful negative result for anyone
> considering GraphRAG on policy text.

### "How do I know the numbers in the deck are real?"

Best possible question. Run it live.

```bash
python scripts/verify_headline_numbers.py
```

> It reads the frozen ranking files and the human relevance judgements, recomputes every
> figure in the deck, and cross-checks against the metrics table written at evaluation time.
> It exits non-zero on any mismatch.

### "You used AI assistance. How much of this is your work?"

> AI assistance is disclosed in the methodology. It was used for question drafting and for
> the R4 answer labels, and that is exactly why R4 is marked exploratory rather than
> confirmatory — those labels have no human-graded overlap, so agreement is not estimable and
> I do not cite them as evidence.
>
> The confirmatory tier is human-graded throughout: I did the relevance judging, the blind
> regrade, and the adjudication of all 14 disagreements. The experimental design,
> preregistration and the decision to invalidate my own runs when they broke the protocol
> were mine.

### "What would change your conclusion?"

> A larger paraphrase set with genuinely adversarial rewrites — no shared content words. If
> dense retrieval won there, my mechanism would be wrong. Also a domain-adapted embedding
> model: I tested general-purpose embeddings, and the honest scope of my claim is that
> general-purpose embeddings underperform here, not that dense retrieval cannot work.

### "Why should anyone care about 22 documents?"

> Because the deployment it describes is real, and the number of documents is not the point —
> the vocabulary structure is. Any bounded, jargon-dense corpus with fixed terminology has
> the same property: legal, medical, regulatory, internal enterprise documentation. The
> corpus is small; the corpus *type* is extremely common.

---

## If he pushes hard

Do not concede claims you can support, and do not defend claims you cannot. The line is:

- **Will defend:** the benchmark, the human grading protocol, the directional finding, the
  mechanism, the cost analysis, the reproducibility.
- **Will concede:** statistical significance, paraphrase construct validity, R4 label
  quality, generalisation beyond English-language Indian policy text.

Being fast and precise about the second list is what makes the first list credible.

If you genuinely do not know something: "I don't know — that isn't something my design can
answer, and here is what would." That answer costs you nothing. Guessing costs you a lot.
