import { dot, norm, orthonormalBasis, project } from "./linear-algebra.ts";
import { passingComplex } from "./passing-complex.ts";
import type { ComplexMode } from "./passing-complex.ts";
import type { CompletedPass } from "../types.ts";

export type HodgeComponent = "net" | "gradient" | "curl" | "harmonic";
export function decomposePassingFlow(
  passes: CompletedPass[],
  teamId: number,
  mode: ComplexMode = "clique",
  removedId: number | null = null,
) {
  const complex = passingComplex(passes, teamId, mode, removedId);
  const flow = complex.edges.map((e) => e.net);
  const gradientBasis = orthonormalBasis(complex.incidence);
  const curlBasis = orthonormalBasis(complex.triangles);
  const gradient = project(flow, gradientBasis),
    curl = project(flow, curlBasis);
  const harmonic = flow.map((v, i) => v - gradient[i] - curl[i]);
  const energy = dot(flow, flow);
  const energies = {
    gradient: dot(gradient, gradient),
    curl: dot(curl, curl),
    harmonic: dot(harmonic, harmonic),
  };
  const denominator = Math.max(1, norm(flow));
  const diagnostics = {
    reconstruction:
      norm(flow.map((v, i) => v - gradient[i] - curl[i] - harmonic[i])) /
      denominator,
    harmonicDivergence:
      Math.hypot(...complex.incidence.map((row) => dot(row, harmonic))) /
      denominator,
    harmonicCurl:
      Math.hypot(...complex.triangles.map((row) => dot(row, harmonic))) /
      denominator,
    orthogonality:
      Math.max(
        Math.abs(dot(gradient, curl)),
        Math.abs(dot(gradient, harmonic)),
        Math.abs(dot(curl, harmonic)),
      ) / Math.max(1, energy),
  };
  return {
    ...complex,
    flow,
    gradient,
    curl,
    harmonic,
    energy,
    energies,
    diagnostics,
    fractions:
      energy > 1e-12
        ? {
            gradient: energies.gradient / energy,
            curl: energies.curl / energy,
            harmonic: energies.harmonic / energy,
          }
        : null,
    firstBetti: complex.edges.length - gradientBasis.length - curlBasis.length,
    reliable: Object.values(diagnostics).every((error) => error < 1e-8),
  };
}
export type HodgeAnalysis = ReturnType<typeof decomposePassingFlow>;
