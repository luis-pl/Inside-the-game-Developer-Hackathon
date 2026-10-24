/** Small dense vector operations; no inversion of singular graph Laplacians. */
export const dot = (a: readonly number[], b: readonly number[]) =>
  a.reduce((sum, value, i) => sum + value * b[i], 0);
export const norm = (v: readonly number[]) => Math.sqrt(dot(v, v));

/** Reorthogonalized modified Gram–Schmidt, adequate for at most 14 participants. */
export function orthonormalBasis(columns: readonly number[][]): number[][] {
  const basis: number[][] = [];
  for (const column of columns) {
    const vector = [...column];
    for (let pass = 0; pass < 2; pass++)
      for (const q of basis) {
        const coefficient = dot(vector, q);
        for (let i = 0; i < vector.length; i++) vector[i] -= coefficient * q[i];
      }
    const length = norm(vector);
    if (length > 1e-10 * Math.max(1, norm(column)))
      basis.push(vector.map((v) => v / length));
  }
  return basis;
}

export function project(
  vector: number[],
  basis: readonly number[][],
): number[] {
  const result = vector.map(() => 0);
  for (const q of basis) {
    const coefficient = dot(vector, q);
    for (let i = 0; i < result.length; i++) result[i] += coefficient * q[i];
  }
  return result;
}
