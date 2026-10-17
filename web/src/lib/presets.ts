export type Example = { id: string; label: string; urls: string[]; text: string; depth: number; engine: string }

// Same inputs as the recorded presets, so the hosted demo replays them instantly.
export const EXAMPLES: Example[] = [
  {
    id: "harvard-vitamin-d",
    label: "Harvard · vitamin D",
    urls: ["https://nutritionsource.hsph.harvard.edu/vitamin-d/"],
    text: "",
    depth: 2,
    engine: "nutrition-coach",
  },
  {
    id: "harvard-zinc",
    label: "Harvard · zinc",
    urls: ["https://nutritionsource.hsph.harvard.edu/zinc/"],
    text: "",
    depth: 1,
    engine: "nutrition-coach",
  },
  {
    id: "olive-oil",
    label: "Healthline · olive oil",
    urls: ["https://www.healthline.com/nutrition/11-proven-benefits-of-olive-oil"],
    text: "",
    depth: 3,
    engine: "nutrition-coach",
  },
  {
    id: "clean",
    label: "A clean study",
    urls: [],
    text: "10.1016/j.jsps.2015.03.013",
    depth: 2,
    engine: "clean-check",
  },
  {
    id: "not-in-graph",
    label: "Not in the graph",
    urls: ["https://www.nhs.uk/live-well/best-way-to-wash-your-hands/"],
    text: "",
    depth: 2,
    engine: "nutrition-coach",
  },
]

export const HARVARD_QUESTION = "Does vitamin D help prevent fractures in older adults?"
export const HARVARD_DRAFT =
  "Vitamin D helps prevent fractures in older adults. Harvard reviews the evidence at https://nutritionsource.hsph.harvard.edu/vitamin-d/."
export const ISHIDA_2004_DOI = "10.1016/j.amjmed.2004.05.019"
export const MCP_URL = "https://mooltrace.h9g8gwz2b559t.ap-south-1.cs.amazonlightsail.com/mcp"
export const REPO_URL = "https://github.com/SidTheKid-dotcom/MoolTrace"
