# ADR 0002: Correction metadata and readable rendering

## Status

Accepted.

## Context

The raw ASR transcript is immutable evidence. The readable transcript is a presentation layer.
A speaker may correct a value, or the ASR output may contain an obvious spelling variant such
as `бекжат бекзат`. Requiring every withdrawn raw phrase to remain verbatim in the readable
text made the pipeline fail even when the raw segment and structured correction object already
preserved that evidence.

## Decision

For every detected correction:

- `original_value` must be an exact substring of the cited raw segment;
- `corrected_value` must appear in the cited readable segment;
- the readable segment may render only the final corrected form;
- the immutable raw segment and `DetectedCorrection` preserve the withdrawn wording;
- `speaker_self_correction` is reserved for explicit correction cues such as `жоқ`,
  `дұрыс айтсам`, `нет`, or `точнее`;
- adjacent near-spelling variants without a correction cue should be classified as
  `asr_normalization` when unambiguous, otherwise as uncertainty.

The validator remains strict about evidence provenance. Relaxing readable rendering does not
allow the model to invent an original value or cite the wrong source segment.

## Consequences

The cleaner no longer blocks the full pipeline merely because it presents only the narrator's
final form. Correction history remains auditable through raw audio, raw ASR, segment IDs, and
the structured correction object.
