export type StepChip = {
  doi?: string | null
  title?: string | null
  url?: string | null
}

export function stepLabel(step: StepChip): string {
  if (step.doi) return step.doi
  if ((step.url || "").startsWith("urn:mooltrace:paste:")) {
    return step.title || "draft"
  }
  return step.url || step.title || "step"
}
