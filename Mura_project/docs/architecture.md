# Mura architecture

## Goal

Mura preserves family memory without pretending that model output is ground truth. Audio, raw ASR, readable transcript, extracted claims, and the materialized family graph are separate layers with separate responsibilities.

## Components

```text
Mobile/web client
  -> Core API (ordinary CPU hosting)
       -> Kaggle ASR worker through HTTPS tunnel
            -> FFmpeg -> Silero VAD -> smart chunks -> GigaAM large_ctc
       <- source-linked raw transcript
       -> DeepSeek cleaner
       -> evidence validation and optional cleaner repair
       -> DeepSeek extractor
       -> Pydantic, graph-reference, and semantic validators
       -> optional extraction repair
       -> mention resolver / review queue
       -> future database and family graph
```

### Kaggle ASR worker

The worker accepts an audio upload and returns an immutable `TranscriptEnvelope`. It never calls DeepSeek and never mutates family data.

Security and stability rules:

- bearer authentication;
- one ASR job at a time;
- upload size and duration limits;
- temporary files are deleted after each request;
- no user-provided filesystem paths;
- Swagger UI is disabled on the public worker;
- a Quick Tunnel URL is treated as temporary.

### Smart chunking

1. Convert audio to 16 kHz mono PCM WAV.
2. Silero VAD identifies speech regions.
3. Nearby regions are merged while the result remains below 22 seconds.
4. Add 450 ms context at both boundaries, keeping the final chunk below 25 seconds.
5. Transcribe every chunk with GigaAM `large_ctc`.
6. Remove a textual boundary duplicate only when the underlying audio ranges overlap.

The last condition protects genuine human repetition.

### Conservative transcript cleaning

The cleaner may add punctuation and capitalization, but it may not translate or silently rewrite facts. An unclear ASR token stays verbatim in the readable transcript and is separately marked as uncertain with no guessed interpretation.

Corrections are typed:

- `speaker_self_correction` preserves both versions spoken by the narrator;
- `asr_normalization` is reserved for an unambiguous spelling or encoding error.

Every correction or uncertain fragment must cite a segment that literally contains the reported raw text. The validator also checks that uncertain text was not deleted and that the same span was not classified as both corrected and uncertain. A failed cleaner contract gets one targeted repair attempt.

### Canonical family semantics

Relationship labels are not free-form text. Each relationship has a canonical type and role pair:

- `parent_child`: `(parent, child)`;
- `spouse`: `(spouse, spouse)`;
- ordered `sibling`: `(older_sibling, younger_sibling)`;
- unordered `sibling`: `(sibling, sibling)`.

This makes direction explicit and prevents grammatical phrasing from reversing the family graph.

People are also classified as `family_member`, `friend`, `roommate`, `acquaintance`, `other_non_family`, or `unknown`. Only family members belong in the шежіре tree; non-family people can still appear in stories and events.

### Semantic integrity checks

Every extracted person, relationship, event, description, story, and unresolved question must reference existing transcript segments. All generated objects start as `unreviewed`; every new story is forced to `private` by the application schema.

In addition to reference checks, the semantic validator verifies that:

- relationship endpoints overlap their cited person evidence;
- canonical relationship roles are valid for the selected type;
- descriptions are not assigned to a different explicitly named person;
- correction and uncertainty evidence occurs in the cited raw segment;
- IDs are unique within every extraction collection.

Invalid output is never silently accepted. The extractor receives one targeted repair attempt; if repair still fails, the API returns a structured upstream error.

### Mention resolution

A mention is an occurrence in one recording. A person is a durable graph node. The first resolver only auto-resolves an exact canonical-name or explicit-alias match with compatible relation context. Ambiguous matches become `needs_review`; unmatched mentions become `new_person` candidates.

## Data invariants

- `RawSegment` text is never overwritten.
- Segment IDs are unique inside a recording.
- Cleaned output covers exactly the same segment IDs as raw output.
- Unclear text remains visible and source-linked.
- All extraction references resolve.
- A relationship cannot connect a mention to itself.
- Relationship role pairs are canonical and directionally explicit.
- A person description cannot be attached to another explicitly named person.
- Non-family people are excluded from the family-tree layer.
- LLM confidence is not equivalent to user confirmation.
- Publication is always an explicit user action.

## Known limitation

Kaggle is a temporary GPU worker. A Quick Tunnel works only while the notebook session, Uvicorn, and `cloudflared` remain alive. The core API treats the worker URL as a replaceable runtime registration, not permanent infrastructure.
