import type { GeneratedBriefing } from "./db";

const SECTION_KEYS = [
  "ai_expansion",
  "ai_technology",
  "expansion_signal",
  "project_vote",
  "disc_golf_outdoors",
  "gaming_entertainment",
  "health_wellness",
  "business_financial_freedom",
  "residential_mortgage",
  "world_watch",
] as const;

const sourceSchema = {
  type: "object",
  additionalProperties: false,
  properties: {
    title: { type: "string" },
    url: { type: "string" },
  },
  required: ["title", "url"],
};

const responseSchema = {
  type: "object",
  additionalProperties: false,
  properties: {
    title: { type: "string" },
    subtitle: { type: "string" },
    one_line_signal: { type: "string" },
    sections: {
      type: "array",
      minItems: 10,
      maxItems: 10,
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          key: { type: "string", enum: SECTION_KEYS },
          title: { type: "string" },
          headline: { type: "string" },
          body: { type: "string" },
          why_it_matters: { type: "string" },
          takeaway: { type: "string" },
          sources: { type: "array", items: sourceSchema, maxItems: 5 },
        },
        required: ["key", "title", "headline", "body", "why_it_matters", "takeaway", "sources"],
      },
    },
    ideas: {
      type: "array",
      minItems: 1,
      maxItems: 3,
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          kind: { type: "string", enum: ["new_project", "project_edit"] },
          related_project: { type: "string" },
          title: { type: "string" },
          summary: { type: "string" },
          why_now: { type: "string" },
          smallest_version: { type: "string" },
          tags: { type: "array", items: { type: "string" }, minItems: 1, maxItems: 5 },
          destination: {
            type: "string",
            enum: ["undecided", "architecture_chat", "codex", "hold"],
          },
        },
        required: [
          "kind",
          "related_project",
          "title",
          "summary",
          "why_now",
          "smallest_version",
          "tags",
          "destination",
        ],
      },
    },
  },
  required: ["title", "subtitle", "one_line_signal", "sections", "ideas"],
};

const EDITORIAL_PLAYBOOK = `
You are the editor of Jason's Daily Personal Briefing. The result should feel like a sharp,
curious human collaborator assembled it for one intelligent reader—not like a generic news digest.

Editorial priorities:
- Major breaking developments, useful ideas, practical takeaways, positive or inspiring stories,
  deep trends others may miss, and original connections across topics.
- U.S. coverage plus major world developments. Prefer primary and authoritative sources.
- Current facts must be researched. Resolve conflicting reports and never invent a source URL.
- Be specific. Use names, dates, numbers, and consequences when they materially help.
- Do not force a story when nothing important happened. Say so briefly and give the most useful signal.
- Keep the voice conversational, grounded, occasionally witty, and free of corporate filler.
- Avoid repeating yesterday's angle or lightly renaming an old project idea.

Write exactly these sections, in this order:
1. AI Expansion — what is newly possible, what it unlocks, how Jason could try it, where it leads.
2. AI & Technology — the most important developments, significance, and practical takeaway.
3. Expansion Signal — connect at least two developments and identify the opportunity underneath them.
4. Project Vote / Build From This — one concrete build idea, why now, and smallest useful version.
5. Disc Golf & Outdoor Life — event/news, why it matters, and one useful skill or experience takeaway.
6. Gaming & Entertainment — releases/updates, what matters, and what is worth watching.
7. Health & Wellness — important update, why it matters, and a practical action. Avoid diagnosis.
8. Business & Financial Freedom — market/economic or entrepreneurial signal, impact, practical takeaway.
9. Residential Mortgage — rates/industry data, operational impact, and an action. Assume mortgage fluency.
10. World Watch — major global development and its U.S., economic, or practical connection.

Project ideas:
- Return 1-3 ideas only when they are genuinely worth keeping.
- Distinguish a new project from an enhancement to something Jason already has.
- Use destination "architecture_chat" when design or scope decisions remain, "codex" when it is ready
  to implement, and "hold" when interesting but not timely.
- Watchtower-related ideas should usually be project edits unless they are truly separate products.
- Look for practical, ambitious, and occasionally surprising intersections without manufacturing novelty.
`;

interface OpenAIResponse {
  output_text?: string;
  output?: Array<{
    type?: string;
    content?: Array<{ type?: string; text?: string }>;
  }>;
}

function extractOutputText(response: OpenAIResponse): string {
  if (response.output_text) return response.output_text;
  for (const item of response.output ?? []) {
    for (const content of item.content ?? []) {
      if (content.type === "output_text" && content.text) return content.text;
    }
  }
  throw new Error("OpenAI returned no structured briefing text.");
}

function sanitizeGeneratedBriefing(value: GeneratedBriefing): GeneratedBriefing {
  const expected = new Set(SECTION_KEYS);
  const seen = new Set(value.sections.map((section) => section.key));
  if (seen.size !== expected.size || [...expected].some((key) => !seen.has(key))) {
    throw new Error("Generated briefing did not contain the required section structure.");
  }

  value.sections.sort(
    (a, b) => SECTION_KEYS.indexOf(a.key as (typeof SECTION_KEYS)[number]) - SECTION_KEYS.indexOf(b.key as (typeof SECTION_KEYS)[number]),
  );

  for (const section of value.sections) {
    section.sources = section.sources.filter((source) => {
      try {
        const url = new URL(source.url);
        return url.protocol === "https:" || url.protocol === "http:";
      } catch {
        return false;
      }
    });
  }
  return value;
}

export async function generateBriefing(
  env: Env,
  briefingDate: string,
  recentContext: { ideaTitles: string[]; signals: string[] },
): Promise<GeneratedBriefing> {
  const response = await fetch("https://api.openai.com/v1/responses", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.OPENAI_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: env.OPENAI_MODEL,
      reasoning: { effort: "medium" },
      tools: [{ type: "web_search", search_context_size: "high" }],
      input: [
        { role: "developer", content: EDITORIAL_PLAYBOOK },
        {
          role: "user",
          content: [
            `Create the Daily Personal Briefing for ${briefingDate} in ${env.TIME_ZONE}.`,
            `Recent project ideas to avoid duplicating: ${recentContext.ideaTitles.join(" | ") || "none"}.`,
            `Recent one-line signals to avoid repeating: ${recentContext.signals.join(" | ") || "none"}.`,
            "Research every time-sensitive section before writing. Return only the required structured output.",
          ].join("\n\n"),
        },
      ],
      text: {
        verbosity: "medium",
        format: {
          type: "json_schema",
          name: "daily_personal_briefing",
          strict: true,
          schema: responseSchema,
        },
      },
    }),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`OpenAI request failed (${response.status}): ${errorText.slice(0, 500)}`);
  }

  const payload = (await response.json()) as OpenAIResponse;
  return sanitizeGeneratedBriefing(JSON.parse(extractOutputText(payload)) as GeneratedBriefing);
}

export { extractOutputText, sanitizeGeneratedBriefing };
