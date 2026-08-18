# Mura ML Core Production Roadmap

**Status:** implementation plan  
**Scope:** multilingual AI core for Kazakh, Russian, English, and code-switched family narratives  
**Primary goal:** turn timestamped ASR transcripts into a conservative, source-linked, incrementally growing family knowledge graph  
**Out of scope for this roadmap:** frontend, payments, general account management, generic backend engineering, mobile design, and infrastructure work that does not improve or operate the ML core.

---

## 1. Why this is an ML Engineering roadmap

Mura is not a standard backend project with an AI call attached. Its central engineering problem is the measurable behavior of a probabilistic multilingual pipeline:

```text
speech
-> ASR
-> multilingual interpretation
-> candidate claims
-> linguistic and semantic validation
-> entity resolution
-> conflict handling
-> source-linked family graph
```

Backend skills still matter because the model pipeline must be served, traced, retried, versioned, monitored, and rolled back. However, Mura does **not** need a generic backend curriculum or infrastructure stack for its own sake.

The roadmap therefore prioritizes:

1. evaluation datasets and error analysis;
2. data and evidence contracts;
3. multilingual linguistic reasoning;
4. constrained LLM extraction;
5. entity resolution across recordings;
6. reproducibility and experiment tracking;
7. model-serving reliability and observability;
8. production monitoring and continuous evaluation.

It explicitly does **not** prioritize Java, Spring, Kafka, Spark, Kubernetes, a feature store, a vector database, or custom model training before there is measured evidence that any of them is necessary.

---

## 2. Corrected conclusions from the Deep Research report

### Keep

The report correctly identifies that:

- GigaAM and DeepSeek are not the main bottleneck;
- literal endpoint matching causes relationship-recall failure;
- raw ASR output must remain immutable;
- DeepSeek should generate candidates rather than define truth;
- accepted claims require provenance;
- invalid isolated objects must be quarantined instead of crashing the whole response;
- a hybrid deterministic/probabilistic reasoning layer is the right direction;
- self-corrections, uncertainty, contradictions, and ambiguity must remain distinct;
- generic WER is insufficient for evaluating the family-graph core.

### Correct

The following recommendations from the report must not be implemented literally:

1. Kazakh `оның` does not encode masculine gender. It means a singular third-person possessor and must be resolved through discourse, number, semantics, and candidate uniqueness.
2. Russian `его` does not by itself identify a male antecedent through ordinary agreement. It still needs discourse resolution.
3. `У Ерлана двое детей` creates a **child-count claim**, not two unnamed `Person` objects or two relationship edges.
4. `Олардың баласы бар` must not invent a named child absent from the evidence.
5. An uncertain claim such as `кажется, в 1942 году` must be preserved as an uncertain claim; it should be excluded from a confirmed profile, not deleted.
6. Exact-name equality is candidate generation, not sufficient evidence for entity merge.
7. Existing child count is not a graph-integrity ceiling unless an explicit closed-world claim such as `ровно двое детей` is present.
8. Multiple spouse edges are not automatically contradictory because marriages may occur at different times.
9. Aliases and orthographic variants are not separate `Person` records.
10. Claims must initially reference `PersonMention`; persistent `Person` IDs are assigned only after entity resolution.
11. Russian is a primary product language and cannot be postponed until a post-MVP phase.
12. Training a custom multilingual dependency parser is not justified without a measured benchmark gap.

---

## 3. Production definition for Mura

“Production” does not mean merely exposing FastAPI endpoints. The ML core reaches production readiness only when all of the following are true:

### Quality

- every released change is evaluated on a versioned gold dataset;
- critical safety metrics have hard release thresholds;
- real failures are converted into regression cases;
- results are reported separately for Kazakh, Russian, English, and code-switching.

### Reproducibility

Every output records:

- ASR model and immutable revision;
- chunker version and parameters;
- cleaner prompt version;
- extractor prompt version;
- linguistic rule-pack version;
- schema version;
- entity-resolution version;
- model provider and model name;
- processing timestamp and latency per stage.

The same input and same versions must be replayable.

### Trust

- raw transcript is immutable;
- no accepted claim exists without provenance;
- unsupported claims cannot silently enter the graph;
- ambiguous references remain reviewable;
- corrections, uncertainty, and testimony conflicts are preserved rather than flattened.

### Reliability

- one malformed LLM object cannot destroy a valid result;
- retries are bounded;
- errors are structured;
- pipeline stages are observable;
- a previous known-good prompt/rule pack can be restored quickly.

### Operational learning

- production traces become new evaluation candidates;
- human confirmations and rejections are captured as labels;
- quality drift, latency, token use, and quarantine behavior are monitored;
- deployment is blocked when quality gates regress.

---

## 4. Target ML architecture

```text
Audio
-> GigaAM ASR
-> immutable timestamped TranscriptEnvelope
-> non-destructive annotation layer
   -> sentence/segment boundaries
   -> script and span language hints
   -> known-name surfaces
   -> kinship lexemes
   -> date/correction/uncertainty markers
   -> safe morphological variants
-> DeepSeek candidate extraction
-> deterministic candidate augmentation
-> candidate fusion and deduplication
-> provenance construction
-> evidence classification
-> bounded discourse/coreference resolver
-> semantic and graph validation
-> Mention -> Person entity resolution
-> claim/conflict store
-> materialized family graph
-> review queue
```

### Ownership of decisions

| Component | Owns | Must not own |
|---|---|---|
| GigaAM | speech-to-text segments | correcting identities or graph facts |
| Cleaner | punctuation, casing, readable text, uncertainty surfacing | silent fact rewriting |
| Linguistic annotator | deterministic high-precision signals | open-ended world knowledge |
| DeepSeek extractor | candidate people, claims, events, descriptions | final acceptance or person merge |
| Coreference resolver | constrained antecedent decisions | guessing when multiple candidates remain |
| Evidence validator | provenance and support classification | deleting uncertain testimony |
| Entity resolver | candidate ranking and safe merges | merging by name alone |
| Graph materializer | confirmed/accepted view | overwriting competing claims |
| Human review | ambiguity and conflict adjudication | rewriting immutable source evidence |

---

## 5. Core data model v2

The current `PersonMention`, `RelationshipClaim`, and quarantine concepts should be retained. The model must be extended without turning aliases into people.

### 5.1 Evidence classes

```python
class EvidenceClass(StrEnum):
    EXPLICIT = "explicit"
    MORPHOLOGICALLY_EXPLICIT = "morphologically_explicit"
    SPEAKER_ANCHORED = "speaker_anchored"
    CONTEXT_RESOLVED = "context_resolved"
    MULTI_EVIDENCE_INFERRED = "multi_evidence_inferred"
    AMBIGUOUS = "ambiguous"
    CONTRADICTORY = "contradictory"
```

Automatic acceptance policy:

- `EXPLICIT`: accept after reference validation;
- `MORPHOLOGICALLY_EXPLICIT`: accept only through a tested deterministic rule;
- `SPEAKER_ANCHORED`: accept when narrator identity is known;
- `CONTEXT_RESOLVED`: accept only when exactly one compatible antecedent remains under a deterministic rule;
- `MULTI_EVIDENCE_INFERRED`: review by default;
- `AMBIGUOUS`: review;
- `CONTRADICTORY`: preserve in a conflict set and review.

Automatic acceptance never means `confirmed`. It means `accepted_unreviewed`.

### 5.2 Provenance

```python
class EvidenceSpan(StrictModel):
    recording_id: str
    segment_id: str
    start: float
    end: float
    raw_text: str
    quote: str | None
    evidence_class: EvidenceClass
    rule_id: str | None
    antecedent_mention_ids: list[str]
```

Separate:

- identity evidence: where a person or name variant is introduced;
- coreference evidence: why a pronoun points to an antecedent;
- claim evidence: where the relationship, date, event, or description is stated;
- resolution evidence: why a mention is linked to a persistent person.

### 5.3 Name variants

```python
class NameVariantType(StrEnum):
    CANONICAL = "canonical"
    ALIAS = "alias"
    NICKNAME = "nickname"
    TRANSLITERATION = "transliteration"
    ORTHOGRAPHIC_VARIANT = "orthographic_variant"
    ASR_VARIANT = "asr_variant"
    INFLECTED_FORM = "inflected_form"

class NameVariant(StrictModel):
    variant_id: str
    mention_id: str | None
    person_id: str | None
    surface_form: str
    normalized_form: str
    variant_type: NameVariantType
    source_segment_ids: list[str]
    verification_status: VerificationStatus
```

`Ереке` may be a real alias for `Ерлан`. `Айгүл`, `Айгуль`, and `Aigul` may be orthographic or transliteration variants. `Мерлан` must not be converted into an alias without supporting evidence.

### 5.4 Generic claims

A family archive contains more than person-to-person edges.

```python
class ClaimType(StrEnum):
    RELATIONSHIP = "relationship"
    BIRTH_DATE = "birth_date"
    DEATH_DATE = "death_date"
    LOCATION = "location"
    PROFESSION = "profession"
    DESCRIPTION = "description"
    EVENT = "event"
    ALIAS = "alias"
    CHILD_COUNT = "child_count"
    OTHER = "other"
```

Each claim requires:

- claim ID;
- claim type;
- subject mention or resolved person;
- typed value;
- evidence spans;
- evidence class;
- assertion mode;
- certainty markers;
- verification status;
- narrator perspective;
- optional conflict-set ID;
- pipeline version metadata.

### 5.5 Coreference links and groups

```python
class CoreferenceLink(StrictModel):
    referring_segment_id: str
    referring_surface: str
    candidate_mention_ids: list[str]
    resolved_mention_ids: list[str]
    rule_id: str
    status: Literal["resolved", "ambiguous", "rejected"]

class MentionGroup(StrictModel):
    group_id: str
    member_mention_ids: list[str]
    source_segment_ids: list[str]
```

Groups are required for references such as `Ерлан мен Динара ... олардың` and `Erlan and Dinara ... they`.

### 5.6 Corrections and conflicts

A self-correction is not a conflict between narrators.

```text
same speaker, same local discourse, explicit replacement
-> self-correction

independent claims with incompatible values
-> conflict set
```

The original retracted value remains stored with status `superseded_by_correction`; the corrected value becomes the active unreviewed candidate.

---

## 6. Linguistic rule strategy

Rules are added only when they can be evaluated independently and achieve very high precision. Morphology is a signal, not permission to over-infer.

### 6.1 Kazakh: highest priority

Implement first:

- speaker anchors: `мен`, `менің`, `біз`, `біздің` and possessive forms;
- explicit kinship patterns: `менің інім Болат`, `үлкен ұлым Ерлан`, `қызымыз Айгүл`;
- named possessors: `Ерланның әйелі Динара`;
- safe normalization of case-marked known names;
- kinship direction and age order: `аға`, `іні`, `әпке`, `сіңлі`, `қарындас`, `ұл`, `қыз`, `әке`, `ана`;
- alias constructions around `деп атайтын`, `деп атайды`, and related naming verbs;
- correction markers: `жоқ`, `дұрыс айтсам`, `емес`, `... болуы керек`;
- uncertainty markers: `сияқты`, `мүмкін`, `шамамен`, `нақты емес`;
- coordinated antecedent groups followed by `олар`, `олардың`.

Important constraints:

- `оның` has no grammatical gender;
- suffix stripping runs against known or detected name candidates and a tested suffix grammar, not unrestricted prefix matching;
- a detected possessive construction must prove both the possessor and the possessed relation before auto-acceptance;
- `біздің балаларымыз` can safely connect the known narrator to the children, but it must not automatically infer a second parent unless that spouse is explicitly established in the same discourse.

### 6.2 Russian: primary priority

Implement in the same milestone as Kazakh:

- speaker anchors and possessives: `я`, `мой`, `моя`, `наш`, `наша` and inflections;
- explicit kinship: `мой младший брат Бекзат`, `наша дочь Айгуль`;
- named possession: `жена Ерлана Динара`, `у Ерлана есть сын Нурлан`;
- name case normalization only for candidate comparison;
- correction constructions: `нет, не X, а Y`, `точнее`, `вернее`, `правильнее сказать`;
- uncertainty: `кажется`, `примерно`, `по-моему`, `возможно`;
- singular and plural discourse references;
- temporal spouse claims without assuming monogamy as an invariant.

Important constraints:

- `его`, `её`, and `их` require discourse resolution;
- `У Ерлана двое детей` creates a count claim until children are named;
- grammatical gender can eliminate incompatible antecedents in Russian but cannot prove identity by itself.

### 6.3 English: secondary but complete

Implement shared architecture support for:

- `my older son Erlan`;
- `Erlan's wife Dinara`;
- `his son Nurlan`;
- `Erlan and Dinara ... their children`;
- aliases and nicknames;
- corrections with `no`, `rather`, `I mean`, `not X but Y`;
- uncertainty with `maybe`, `probably`, `I think`, `around`.

English should reuse the same evidence classes and discourse state rather than creating a separate pipeline.

### 6.4 Code-switching

The original text and script remain unchanged. Normalized matching is stored alongside, never in place of, the source.

Rules must support examples such as:

- `Ерланның wife Динара`;
- `После школы Ерлан Қарағандыға көшті`;
- `Оның son Нұрлан`;
- `Қазір ол Алматыда тұрады and works as an engineer`.

Span-level language identification is adopted only if benchmark evidence shows it improves rule routing. A full language-ID model is not a prerequisite for the first version; script, lexicons, and local patterns may be sufficient.

---

## 7. Discourse and coreference framework

### 7.1 Discourse state

Maintain a bounded state per recording:

```python
class DiscourseEntityState:
    mention_id: str
    grammatical_number: str | None
    grammatical_gender: str | None
    semantic_type: str
    last_segment_index: int
    subject_recency: int
    mention_recency: int
    group_ids: list[str]
```

Do not use one opaque confidence number. Candidate elimination and rule evidence must be inspectable.

### 7.2 Safe automatic cases

Accept a context-resolved reference only when:

1. exactly one candidate remains after deterministic filtering;
2. the candidate is inside a bounded window;
3. number and, where applicable, gender are compatible;
4. semantic type is compatible;
5. no coordinated competing candidate has equal support;
6. the resulting claim passes graph validation;
7. the complete provenance chain is stored;
8. the rule has passed its benchmark precision gate.

### 7.3 Mandatory review cases

Quarantine when:

- two or more plausible antecedents remain;
- a reference crosses a topic boundary without a re-mention;
- a pronoun is compatible with a recent group and a recent individual;
- ASR corruption changes an endpoint name;
- a relationship depends only on LLM explanation without deterministic or explicit evidence;
- a proposed merge would combine same-name relatives without graph support.

---

## 8. Evaluation-driven development

No core refactor is merged before the benchmark exists.

### 8.1 Dataset layers

#### Layer A: deterministic unit fixtures

Small single-construction cases. Minimum 80 fixtures:

- 25 Kazakh;
- 20 Russian;
- 10 English;
- 25 code-switched.

#### Layer B: discourse fixtures

Minimum 40 multi-sentence cases:

- singular pronouns;
- plural antecedents;
- topic shifts;
- two compatible antecedents;
- speaker-relative constructions;
- alias introduction and reuse;
- same-name relatives.

#### Layer C: multi-recording family fixtures

Minimum 20 scenarios containing two to five recordings:

- alias reuse across recordings;
- repeated facts;
- conflicting dates;
- self-correction versus testimony conflict;
- same name, different generations;
- friends and relatives in the same archive;
- false-merge traps.

#### Layer D: anonymized real narratives

At least:

- one long Kazakh-Russian story already used by the project;
- two additional narrators before a production claim;
- noisy and spontaneous speech;
- hand-verified transcript and expected claim graph.

Private source data must not be committed. Store only approved anonymized fixtures or local dataset references.

### 8.2 Required metrics

```text
person mention precision / recall / F1
relationship precision / recall / F1
relationship direction accuracy
coreference link accuracy
alias precision / recall
name-variant normalization precision / recall
entity-resolution pairwise precision / recall / F1
false merge rate
false split rate
description-to-person attribution accuracy
correction detection precision / recall / F1
conflict detection precision / recall / F1
evidence segment precision / recall
provenance completeness
unsupported-claim acceptance rate
correct-claim quarantine rate
critical graph violation count
latency and token use by stage
```

Report every metric by language bucket and construction family, not only as a global mean.

### 8.3 Proposed release gates

These are internal targets to be validated and adjusted with real data; they are not claims about arbitrary speech.

#### Hard safety gates

- provenance completeness: **100%**;
- unknown segment references: **0**;
- self-relationships: **0**;
- accepted claims with no supporting evidence: **0**;
- critical graph violations: **0**;
- false merges on the gold benchmark: **0**;
- relationship direction accuracy: **>= 99%**;
- unsupported-claim acceptance rate: **<= 1%**, with **0** on critical family relationships in the release set.

#### Quality gates

- relationship precision: **>= 97%**;
- relationship recall: **>= 90%**;
- alias precision: **>= 98%**;
- alias recall: **>= 90%**;
- correction F1: **>= 95%**;
- coreference accuracy on auto-accepted class D: **>= 97%**;
- correct-claim quarantine rate: **<= 10% overall** and **<= 5% for evidence classes A-C**;
- evidence segment accuracy: **>= 95%**.

A change is rejected if aggregate F1 improves by accepting more unsupported claims beyond the safety gate.

### 8.4 Experiment loop

Every improvement follows:

```text
error hypothesis
-> add or identify failing fixture
-> measure baseline
-> implement smallest rule/prompt/model change
-> run full benchmark
-> inspect false positives and false negatives
-> merge only if safety and regression gates pass
```

Never tune only against the one long recording.

---

## 9. Implementation phases

## Phase 0 — Freeze and measure the current baseline

**Goal:** make the current behavior reproducible before changing it.

Deliverables:

- version fields for prompts, rules, schema, resolver, and extractor;
- fixture adapter for saved `TranscriptEnvelope` payloads;
- baseline evaluation command;
- per-stage latency and token accounting;
- saved baseline report.

Repository work:

```text
src/mura/versioning.py
src/mura/evaluation/
benchmarks/manifest.yaml
benchmarks/synthetic/
scripts/evaluate_core.py
```

Exit gate:

- the same fixture produces structurally identical results under fixed versions;
- current metrics are committed as a baseline artifact;
- no production logic changes are mixed into this phase.

## Phase 1 — Gold benchmark and evaluation harness

**Goal:** create the test system that decides whether later changes are improvements.

Deliverables:

- typed benchmark schema;
- initial deterministic, discourse, and multi-recording fixtures;
- graph-aware scorer;
- machine-readable JSON report and human-readable Markdown report;
- language and construction breakdowns.

Exit gate:

- scorer unit tests pass;
- benchmark annotations are internally consistent;
- current main can be evaluated with one command.

## Phase 2 — Evidence and claim model v2

**Goal:** represent why each claim is believed.

Deliverables:

- `EvidenceClass`;
- `EvidenceSpan`;
- `NameVariant`;
- generic claim metadata;
- `CoreferenceLink` and `MentionGroup`;
- explicit correction and conflict lifecycle;
- compatibility adapter from current extraction JSON.

Exit gate:

- 100% provenance on benchmark outputs;
- old fixtures remain processable;
- no alias becomes a fake `Person`.

## Phase 3 — Deterministic multilingual linguistic layer

**Goal:** safely recover obvious relationships and anchors without depending on LLM guesses.

Deliverables:

```text
src/mura/linguistics/common.py
src/mura/linguistics/kazakh.py
src/mura/linguistics/russian.py
src/mura/linguistics/english.py
src/mura/linguistics/kinship.py
src/mura/linguistics/corrections.py
src/mura/linguistics/names.py
```

Start with lexicons and audited rules. Evaluate external morphological or dependency tools behind interfaces; adopt them only if they improve the gold benchmark without violating latency and precision gates.

Exit gate:

- deterministic rule precision is 100% on its declared scope;
- speaker-anchored and named-possessor recall improves measurably;
- unrestricted prefix matching is removed or restricted to safe candidate contexts.

## Phase 4 — Discourse and coreference v2

**Goal:** resolve bounded unambiguous references while preserving ambiguity.

Deliverables:

- discourse state tracker;
- singular antecedent rules;
- coordinated group mentions;
- context boundaries and reset rules;
- inspectable `CoreferenceLink` output;
- review reasons for ambiguous cases.

Exit gate:

- auto-accepted class-D accuracy >= 97%;
- no safety-gate regression;
- ambiguous two-candidate fixtures remain unresolved.

## Phase 5 — Constrained DeepSeek extraction

**Goal:** improve extraction recall while reducing hallucinated endpoints.

Changes:

- DeepSeek receives known segment IDs, candidate mention anchors, kinship lexemes, and optional deterministic annotations;
- output remains strict JSON;
- extraction and repair prompts are versioned separately;
- candidate claims reference mentions, not persistent people;
- LLM explanations are never accepted as evidence by themselves;
- sanitizer keeps valid objects and quarantines isolated failures.

Experiments:

- current free extraction versus anchor-constrained extraction;
- one-pass versus extractor plus bounded repair;
- raw transcript only versus raw plus annotations;
- per-segment extraction versus complete-recording extraction.

Exit gate:

- relationship recall >= 90%;
- relationship precision >= 97%;
- unsupported-claim acceptance remains within gate;
- latency and token cost are documented.

## Phase 6 — Multi-recording entity resolution

**Goal:** grow one family archive over time without false merges.

Candidate signals:

- canonical or normalized name;
- explicit alias evidence;
- relation to narrator;
- generation;
- parents, spouse, children, and siblings;
- age/date compatibility;
- location and event overlap;
- narrator identity;
- family archive boundary.

Rules:

- never merge across `family_id`;
- exact name alone does not merge;
- same-name relatives remain separate until graph evidence disambiguates them;
- deterministic alias evidence may auto-resolve;
- fuzzy or ASR-suspected variants require corroboration or review;
- no single opaque confidence score controls the merge.

Exit gate:

- false merge rate is zero on the release benchmark;
- false split rate is reported and below the chosen release threshold;
- every resolution has an inspectable reason and evidence chain.

## Phase 7 — Conflict, correction, and graph materialization

**Goal:** turn claims into a coherent view without deleting testimony.

Deliverables:

- conflict-set builder;
- self-correction supersession;
- temporal relationship support;
- materialized active graph from accepted claims;
- separate confirmed, accepted-unreviewed, uncertain, and conflicting views;
- derived kinship computation from base edges.

Exit gate:

- conflicting dates are both retained;
- self-corrected values are distinguishable from independent conflict;
- graph materialization is deterministic and reversible.

## Phase 8 — Robustness and adversarial testing

**Goal:** ensure success is not limited to clean synthetic sentences.

Test mutations:

- missing punctuation;
- ASR spelling variants;
- code-switching at word boundaries;
- chunk-boundary repetitions;
- false starts and repeated names;
- unnamed count claims;
- same-name people;
- topic shifts;
- long-distance pronouns;
- friends mixed with relatives;
- deliberately unsupported LLM outputs;
- malformed but partially valid JSON.

Exit gate:

- safety gates pass on adversarial suites;
- no whole-result failure from one malformed object;
- degradation by language and mutation type is documented.

## Phase 9 — Performance and cost engineering

**Goal:** optimize only after quality stabilizes.

Measure:

- ASR real-time factor;
- cleaner latency;
- extractor latency;
- retries;
- tokens and monetary cost per audio minute;
- memory and GPU use;
- end-to-end p50/p95;
- quarantine volume per recording.

Initial service targets:

- upload/job creation p95 < 500 ms;
- ASR p95 RTF <= 0.2 on supported audio lengths;
- reasoning p95 <= 120 seconds for a ten-minute transcript;
- end-to-end asynchronous completion p95 <= 180 seconds for ten minutes;
- no silent job loss;
- bounded retries and explicit failure stage.

Optimization candidates:

- avoid sending irrelevant segments to repair;
- cache immutable deterministic annotations;
- use prompt-prefix caching where supported;
- batch independent validation work;
- reprocess from transcript without rerunning ASR;
- preserve a faster fallback prompt version only if it passes the same quality gates.

## Phase 10 — MLOps and production operation

**Goal:** create a continuous quality loop rather than a one-time demo.

### Experiment and evaluation management

Start lightweight with versioned JSONL/YAML fixtures and generated reports in CI. Introduce MLflow when repeated prompt/rule experiments need centralized traces, comparison, human labels, and production evaluation. Do not add it before the evaluation harness itself is correct.

### Tracing

Trace each stage:

```text
recording
  ASR
    conversion
    VAD
    chunking
    model inference
  cleaner
  linguistic annotation
  extractor
  candidate fusion
  evidence validation
  coreference
  entity resolution
  graph materialization
```

Log IDs and metadata, not unrestricted private audio or family text. Redaction and data-retention rules are mandatory.

### CI release gates

Every pull request that changes prompts, rules, schemas, models, or resolution logic runs:

- unit tests;
- benchmark evaluation;
- comparison against the approved baseline;
- hard safety-gate checks;
- latency smoke test;
- schema compatibility test;
- secret and dependency scans already present in the repository.

### Deployment strategy

- shadow-run a new pipeline version on saved or approved traffic;
- compare old and new outputs;
- canary by version, not by editing prompts in place;
- keep immediate rollback to the previous prompt/rule pack;
- never migrate stored claims destructively without provenance-preserving reprocessing.

### Production monitoring

Monitor:

- stage failures and retries;
- p50/p95 latency;
- token/cost per minute;
- quarantine rate by evidence class;
- human rejection rate of auto-accepted claims;
- human acceptance rate of quarantined claims;
- false-merge reports;
- language distribution and code-switching rate;
- ASR name correction rate;
- schema and prompt version distribution;
- drift between benchmark and real traffic.

Production traces and corrected review items feed the next benchmark version.

Exit gate:

- one full release, rollback, and replay drill succeeds;
- real review feedback can be converted into fixtures;
- monitoring detects an intentionally injected quality regression.

---

## 10. Tool adoption policy

Mura should not become a collection of fashionable tools.

### Required now

- Python;
- Pydantic contracts;
- pytest-based unit and regression testing;
- GigaAM;
- DeepSeek API;
- FastAPI boundary for integration;
- structured logs and explicit pipeline versions.

### Evaluate behind interfaces

- Kazakh morphological analyzers;
- Russian morphology libraries;
- Universal Dependencies parsers;
- span-level language identification;
- MLflow tracing/evaluation;
- OpenTelemetry export.

A tool is adopted only when an ablation experiment shows measurable benefit on Mura metrics.

### Not required before evidence appears

- Java or Spring;
- custom dependency-parser training;
- model fine-tuning;
- Kubernetes;
- Kafka;
- Spark;
- Airflow;
- a feature store;
- a vector database;
- Neo4j;
- a separate microservice per pipeline stage.

---

## 11. Repository mapping

### Retain

```text
services/kaggle_asr/
src/mura/deepseek/
src/mura/extraction_sanitizer.py
src/mura/domain/models.py
src/mura/resolution.py
existing quarantine and reference validation
existing security and CI workflows
```

### Refactor

```text
src/mura/relationship_evidence.py
  -> replace surface-only support with EvidenceSpan + linguistic/coreference support

src/mura/validation.py
  -> split reference validation, evidence validation, graph validation, and release policy

src/mura/deepseek/prompts.py
  -> versioned prompts with anchor-constrained extraction

src/mura/pipeline.py
  -> explicit traceable stages and version metadata
```

### Add

```text
src/mura/linguistics/
src/mura/coreference/
src/mura/claims/
src/mura/conflicts/
src/mura/evaluation/
src/mura/versioning.py
benchmarks/
scripts/evaluate_core.py
docs/ML_CORE_PRODUCTION_ROADMAP.md
```

### Deprecate after replacement

- unrestricted string-prefix name matching;
- LLM confidence as an operational decision signal;
- relationship acceptance based only on literal endpoint co-occurrence;
- direct mention-to-person merges by exact name;
- any rule that assumes a maximum number of children or one lifetime spouse.

---

## 12. Milestone sequence

```text
M0  Current baseline is reproducible
M1  Benchmark and scorer are trusted
M2  Evidence/claim schema v2 is complete
M3  Kazakh + Russian deterministic rules pass precision gates
M4  Bounded coreference improves recall safely
M5  DeepSeek extraction is anchor-constrained and quality-gated
M6  Cross-recording entity resolution has zero benchmark false merges
M7  Conflicts and graph materialization are deterministic
M8  Robustness/adversarial suites pass
M9  Latency and cost meet service targets
M10 Production tracing, rollback, and continuous evaluation work
```

We do not skip directly to MLOps tooling. The production path is:

```text
benchmark
-> evidence contracts
-> linguistic reasoning
-> constrained extraction
-> entity resolution
-> robustness
-> performance
-> operation
```

---

## 13. Immediate next work

The next implementation PR must contain only Phase 0 and Phase 1 foundations:

1. pipeline-version metadata;
2. benchmark schemas;
3. synthetic fixture structure;
4. graph-aware metric implementation;
5. baseline evaluator command;
6. baseline report for the current `main` behavior.

It must **not** change relationship logic yet. Once the evaluator is trusted, every later core change becomes measurable and reversible.

---

## 14. Reference direction

Useful production patterns to evaluate during later phases:

- MLflow GenAI evaluation and production-trace evaluation: https://mlflow.org/docs/latest/genai/eval-monitor/
- MLflow tracing: https://mlflow.org/docs/latest/genai/tracing
- OpenTelemetry Python traces and metrics: https://opentelemetry.io/docs/languages/python/
- Universal Dependencies resources: https://universaldependencies.org/

These tools support the roadmap; they do not replace Mura-specific gold data, scorers, or linguistic rules.
