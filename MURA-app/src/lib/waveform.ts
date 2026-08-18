function hashSeed(seed: string): number {
  let h = 1779033703 ^ seed.length;
  for (let i = 0; i < seed.length; i++) {
    h = Math.imul(h ^ seed.charCodeAt(i), 3432918353);
    h = (h << 13) | (h >>> 19);
  }
  return h >>> 0;
}

function mulberry32(seed: number): () => number {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Deterministic speech-like bar heights (0.12–1) for a story’s waveform, so
 * the same recording always draws the same shape.
 */
export function seededWaveform(seed: string, count: number): number[] {
  const rand = mulberry32(hashSeed(seed));
  const raw = Array.from({ length: count }, () => 0.12 + rand() ** 1.4 * 0.88);
  // Soften with a neighbor average so it reads as speech, not static.
  return raw.map((v, i) => {
    const prev = raw[i - 1] ?? v;
    const next = raw[i + 1] ?? v;
    return (prev + v * 2 + next) / 4;
  });
}
