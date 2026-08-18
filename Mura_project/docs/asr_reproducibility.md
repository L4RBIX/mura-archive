# ASR reproducibility and evaluation

Mura loads `ai-sage/GigaAM-Multilingual` from the immutable Hugging Face commit
`ac7c6db08133f83478451a659f8470ee8ab47a2d`, corresponding to the `large_ctc`
variant selected for the worker. The upstream model requires custom Transformers code. Mura
therefore downloads the complete snapshot at that exact commit, computes SHA-256 digests for the
configuration, custom code and weight artifact, and then loads only from the local snapshot with
`local_files_only=True`.

This is a constrained exception to the normal rule against `trust_remote_code=True`. Changing the
model requires a code review of the new immutable snapshot and an explicit commit update. Mutable
branches such as `large_ctc`, `main` or `latest` are not accepted at runtime.

Silero VAD is pinned to package version `6.2.1`. The chunker is versioned independently as
`silero-smart-v2-exact-overlap`. Chunk-boundary de-duplication uses exact normalized token overlap,
not fuzzy similarity, and limits removable tokens using the measured audio overlap duration.

`mura-evaluate-asr` computes WER, CER, insertion/deletion/substitution counts, language buckets,
boundary merge accuracy and repetition preservation. The committed dataset is synthetic and only
validates evaluator/chunker contracts. It must not be presented as live GigaAM accuracy.

Live evaluation uses `mura-evaluate-asr-live` on an approved local manifest. Every fixture must have
an explicit public license or consent record. Private family audio must never be committed to the
repository or uploaded as a public CI artifact. Audio paths in the manifest must be relative and
must stay below the manifest directory; the runner rejects absolute paths and `..` traversal. The
manual workflow also caps each fixture at 1,800 seconds.

The committed WER/CER normalizer uses Unicode NFKC, case folding, punctuation removal and whitespace
collapse. It does not convert numerals to words. Results are comparable only when the same evaluator
version and normalization policy are used.
