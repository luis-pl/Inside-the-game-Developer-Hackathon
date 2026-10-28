export type ChartSample = { timeMs: number; value: number | null };

/** Break the chart at missing values or gaps; never invent tracking evidence. */
export function chartSegments(samples: ChartSample[], maxGapMs: number) {
  const segments: ChartSample[][] = [];
  let current: ChartSample[] = [];
  for (const sample of samples) {
    if (sample.value === null || !Number.isFinite(sample.value)) {
      if (current.length) segments.push(current);
      current = [];
      continue;
    }
    if (current.length && sample.timeMs - current.at(-1)!.timeMs > maxGapMs) {
      segments.push(current);
      current = [];
    }
    current.push(sample);
  }
  if (current.length) segments.push(current);
  return segments;
}

export function nearestSample(samples: ChartSample[], timeMs: number) {
  if (!samples.length) return -1;
  let lo = 0,
    hi = samples.length - 1;
  while (lo < hi) {
    const mid = Math.floor((lo + hi) / 2);
    if (samples[mid].timeMs < timeMs) lo = mid + 1;
    else hi = mid;
  }
  return lo > 0 &&
    timeMs - samples[lo - 1].timeMs <= samples[lo].timeMs - timeMs
    ? lo - 1
    : lo;
}
