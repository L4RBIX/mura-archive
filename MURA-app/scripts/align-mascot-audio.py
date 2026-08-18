"""Align each mascot script to its recording's real speech timing.

Words are not spread evenly across the file. The recording is decoded, an RMS
envelope is measured, and silence is detected — so pauses stay empty, sentence
boundaries land on the actual breaths the speaker took, and a fast clause gets
proportionally less time than a slow one.

Method
  1. afconvert the mp3 to 16kHz mono PCM (macOS built-in; no ffmpeg needed).
  2. RMS envelope in 10ms frames; adaptive threshold from the noise floor.
  3. Speech segments = runs above threshold, with short gaps bridged.
  4. Sentence boundaries in the script are anchored to the longest real pauses.
  5. Within each sentence, words are laid out over that sentence's speech time
     in proportion to syllable count (Russian vowels + Latin vowel groups),
     which tracks how long each word actually takes to say.

Run:  python3 scripts/align-mascot-audio.py
Out:  src/lib/mascot/cue-timings.generated.ts
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO = os.path.join(ROOT, "public/audio")
OUT = os.path.join(ROOT, "src/lib/mascot/cue-timings.generated.ts")

FRAME_MS = 10
# A gap shorter than this is within-phrase (stop consonants, glottal breaks).
MIN_PAUSE_MS = 150
MIN_SEGMENT_MS = 90

INTRO = (
    "Здравствуйте. Я — Мура́. Я помогу сохранить ваши семейные воспоминания. "
    "Просто расскажите историю так, как вы её помните."
)
ASK = (
    "Вы можете спрашивать меня о семейных воспоминаниях. Я отвечаю только на "
    "основе подтверждённых историй и никогда не придумываю факты."
)
PROCESSING = "Спасибо. Я обрабатываю воспоминание. Это займёт всего несколько секунд."
MUSTAFA = (
    "Сегодня ваш внук Мустафарыза участвовал в Kazakhstan Central Asia FIRST "
    "Championship. Его команда заняла третье место в номинации Connect Award и "
    "второе место в номинации Best Uniform Award. Вот фотография с этого события."
)

# Scripts are verbatim from the recording brief and must not be edited.
CLIPS = [
    ("/audio/intro-alina.mp3", "intro-alina.mp3", INTRO),
    ("/audio/intro-ariana.mp3", "intro-ariana.mp3", INTRO),
    ("/audio/ask-alina.mp3", "ask-alina.mp3", ASK),
    ("/audio/processing-alina.mp3", "processing-alina.mp3", PROCESSING),
    ("/audio/mustafa-alina.mp3", "mustafa-alina.mp3", MUSTAFA),
    ("/audio/mustafa-ariana.mp3", "mustafa-ariana.mp3", MUSTAFA),
]

VOWELS = set("аеёиоуыэюяАЕЁИОУЫЭЮЯ")
LATIN_VOWELS = set("aeiouyAEIOUY")


def syllables(word: str) -> int:
    """Rough duration weight. Russian ≈ one vowel per syllable; Latin groups."""
    cyr = sum(1 for ch in word if ch in VOWELS)
    if cyr:
        return cyr
    groups, prev = 0, False
    for ch in word:
        is_v = ch in LATIN_VOWELS
        if is_v and not prev:
            groups += 1
        prev = is_v
    return max(1, groups)


def decode(path: str) -> tuple[list[float], int]:
    """mp3 → 16kHz mono PCM → per-frame RMS envelope."""
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "a.wav")
        subprocess.run(
            ["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", path, wav],
            check=True, capture_output=True,
        )
        with wave.open(wav, "rb") as w:
            rate = w.getframerate()
            raw = w.readframes(w.getnframes())

    import array
    samples = array.array("h")
    samples.frombytes(raw)
    per = int(rate * FRAME_MS / 1000)
    env = []
    for i in range(0, len(samples) - per, per):
        acc = 0
        for s in samples[i : i + per]:
            acc += s * s
        env.append((acc / per) ** 0.5 / 32768.0)
    return env, rate


def speech_segments(env: list[float]) -> list[tuple[int, int]]:
    """Frame-index runs of speech, with sub-threshold micro-gaps bridged."""
    ordered = sorted(env)
    floor = ordered[int(len(ordered) * 0.10)]
    peak = ordered[int(len(ordered) * 0.95)]
    threshold = max(floor * 2.2, peak * 0.075)

    voiced = [e > threshold for e in env]
    bridge = MIN_PAUSE_MS // FRAME_MS
    segs: list[list[int]] = []
    for i, on in enumerate(voiced):
        if not on:
            continue
        if segs and i - segs[-1][1] <= bridge:
            segs[-1][1] = i
        else:
            segs.append([i, i])
    keep = [(a, b) for a, b in segs if (b - a) * FRAME_MS >= MIN_SEGMENT_MS]
    return keep or [(0, len(env) - 1)]


def sentences_of(script: str) -> list[list[str]]:
    """Split on sentence-final punctuation, keeping the punctuation attached."""
    parts = re.split(r"(?<=[.!?])\s+", script.strip())
    return [p.split() for p in parts if p.strip()]


def align(script: str, env: list[float], duration: float) -> list[dict]:
    segs = speech_segments(env)
    sents = sentences_of(script)

    # Gaps between speech segments, longest first — these are the real breaths.
    gaps = [
        (segs[i + 1][0] - segs[i][1], i)
        for i in range(len(segs) - 1)
    ]
    gaps.sort(reverse=True)
    # Anchor sentence boundaries to the longest pauses, then restore order.
    cuts = sorted(idx for _, idx in gaps[: max(0, len(sents) - 1)])

    if len(segs) < len(sents):
        # This speaker ran sentences together without a measurable breath
        # between each one. Reusing a segment to fill the gap would give two
        # sentences the same span and make their words overlap, so lay the
        # whole script across all the speech time as a single run instead.
        sents = [[w for sentence in sents for w in sentence]]
        groups: list[list[tuple[int, int]]] = [segs]
    else:
        groups = []
        start = 0
        for cut in cuts:
            groups.append(segs[start : cut + 1])
            start = cut + 1
        groups.append(segs[start:])
        # More pauses than sentences: fold the surplus into the previous run.
        while len(groups) > len(sents):
            groups[-2].extend(groups.pop())

    out: list[dict] = []
    for words, group in zip(sents, groups):
        if not group:
            group = [segs[-1]]
        spans = [(a * FRAME_MS / 1000, (b + 1) * FRAME_MS / 1000) for a, b in group]
        speech = sum(e - s for s, e in spans)
        weights = [syllables(w) for w in words]
        total = sum(weights) or 1

        # Walk the sentence's speech time, skipping its internal pauses, so a
        # word can never be scheduled inside silence.
        cursor, span_i, used = 0.0, 0, 0.0
        for word, weight in zip(words, weights):
            need = speech * weight / total
            start_t = spans[span_i][0] + (cursor - used)
            remaining = need
            while remaining > 1e-9 and span_i < len(spans):
                s, e = spans[span_i]
                left = e - (s + (cursor - used))
                if remaining <= left + 1e-9:
                    cursor += remaining
                    remaining = 0
                else:
                    cursor += left
                    remaining -= left
                    used = cursor
                    span_i += 1
                    if span_i < len(spans):
                        pass
            end_span = min(span_i, len(spans) - 1)
            end_t = spans[end_span][0] + (cursor - used)
            out.append(
                {
                    "word": word,
                    "startMs": int(round(max(0.0, start_t) * 1000)),
                    "endMs": int(round(min(duration, end_t) * 1000)),
                }
            )
    # Monotonic, non-degenerate.
    for i in range(1, len(out)):
        out[i]["startMs"] = max(out[i]["startMs"], out[i - 1]["startMs"] + 40)
        out[i]["endMs"] = max(out[i]["endMs"], out[i]["startMs"] + 60)
    return out


def duration_of(path: str) -> float:
    info = subprocess.run(["afinfo", path], check=True, capture_output=True, text=True)
    m = re.search(r"estimated duration:\s*([\d.]+)", info.stdout)
    return float(m.group(1)) if m else 0.0


def main() -> int:
    entries = []
    for url, filename, script in CLIPS:
        path = os.path.join(AUDIO, filename)
        if not os.path.exists(path):
            print(f"  MISSING {filename}", file=sys.stderr)
            return 1
        duration = duration_of(path)
        env, _ = decode(path)
        segs = speech_segments(env)
        timings = align(script, env, duration)
        speech_s = sum((b - a + 1) * FRAME_MS for a, b in segs) / 1000
        print(
            f"  {filename:24s} {duration:6.2f}s  speech {speech_s:5.2f}s  "
            f"segments {len(segs):3d}  words {len(timings):3d}"
        )
        entries.append(
            {"url": url, "durationMs": int(round(duration * 1000)), "words": timings}
        )

    body = ",\n".join(
        "  {}: {}".format(
            json.dumps(e["url"]),
            json.dumps(
                {"durationMs": e["durationMs"], "words": e["words"]},
                ensure_ascii=False,
            ),
        )
        for e in entries
    )
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(
            "// GENERATED by scripts/align-mascot-audio.py — do not edit by hand.\n"
            "// Word timings measured from each recording's own RMS envelope, so\n"
            "// pauses stay empty and sentence boundaries sit on real breaths.\n"
            "// Re-run the script after replacing any mascot audio file.\n\n"
            "export interface CueWordTiming {\n"
            "  word: string;\n"
            "  startMs: number;\n"
            "  endMs: number;\n"
            "}\n\n"
            "export interface CueTiming {\n"
            "  durationMs: number;\n"
            "  words: CueWordTiming[];\n"
            "}\n\n"
            "/** Keyed by the clip's public URL. */\n"
            "export const CUE_TIMINGS: Record<string, CueTiming> = {\n"
            f"{body},\n"
            "};\n"
        )
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
