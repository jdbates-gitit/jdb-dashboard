import { describe, expect, it } from "vitest";
import { extractOutputText, sanitizeGeneratedBriefing } from "../src/briefing";
import { deleteIdea, selectPublicSections, type BriefingSection } from "../src/db";
import worker, { classifyHostname, localDate, localHour } from "../src/index";

describe("briefing helpers", () => {
  it("extracts structured output text", () => {
    expect(
      extractOutputText({
        output: [{ content: [{ type: "output_text", text: "{\"ok\":true}" }] }],
      }),
    ).toBe("{\"ok\":true}");
  });

  it("converts scheduled UTC time to Houston time", () => {
    const summer = new Date("2026-08-19T13:00:00Z");
    expect(localDate("America/Chicago", summer)).toBe("2026-08-19");
    expect(localHour("America/Chicago", summer)).toBe(8);
  });

  it("rejects a briefing missing required sections", () => {
    expect(() =>
      sanitizeGeneratedBriefing({
        title: "Daily briefing",
        subtitle: "",
        one_line_signal: "Signal",
        sections: [],
        ideas: [],
      }),
    ).toThrow(/required section structure/);
  });

  it("keeps the Project Vote out of the public edition", () => {
    const section = (key: string): BriefingSection => ({
      key,
      title: key,
      headline: "Headline",
      body: "Body",
      why_it_matters: "Why it matters",
      takeaway: "Takeaway",
      sources: [],
    });

    expect(selectPublicSections([section("ai_technology"), section("project_vote")])).toEqual([
      section("ai_technology"),
    ]);
  });

  it("permanently deletes an idea from D1", async () => {
    let boundId = "";
    const db = {
      prepare: () => ({
        bind: (...values: unknown[]) => ({
          run: async () => {
            boundId = String(values[0]);
            return {
              success: true,
              results: [],
              meta: {
                duration: 0,
                size_after: 0,
                rows_read: 0,
                rows_written: 1,
                last_row_id: 0,
                changed_db: true,
                changes: 1,
              },
            };
          },
        }),
      }),
    };

    await expect(deleteIdea(db, "idea-123")).resolves.toBe(true);
    expect(boundId).toBe("idea-123");
  });

  it("separates private, public, and preview hostnames", () => {
    expect(classifyHostname("dashboard.jdb-builds.com")).toBe("private");
    expect(classifyHostname("briefing.jdb-builds.com")).toBe("public");
    expect(classifyHostname("jdb-dashboard.jdbates.workers.dev")).toBe("unknown");
  });

  it("does not expose private APIs on the public or preview hostnames", async () => {
    const env = { ADMIN_EMAIL: "jdbates@gmail.com" } as Env;
    const publicIdeas = await worker.fetch(
      new Request("https://briefing.jdb-builds.com/api/ideas"),
      env,
    );
    const publicGenerate = await worker.fetch(
      new Request("https://briefing.jdb-builds.com/api/generate", { method: "POST" }),
      env,
    );
    const publicDelete = await worker.fetch(
      new Request("https://briefing.jdb-builds.com/api/ideas/00000000-0000-0000-0000-000000000000", { method: "DELETE" }),
      env,
    );
    const previewIdeas = await worker.fetch(
      new Request("https://jdb-dashboard.jdbates.workers.dev/api/ideas"),
      env,
    );
    const unauthenticatedPrivateIdeas = await worker.fetch(
      new Request("https://dashboard.jdb-builds.com/api/ideas"),
      env,
    );
    const unauthenticatedPrivateDelete = await worker.fetch(
      new Request("https://dashboard.jdb-builds.com/api/ideas/00000000-0000-0000-0000-000000000000", { method: "DELETE" }),
      env,
    );

    expect(publicIdeas.status).toBe(404);
    expect(publicGenerate.status).toBe(405);
    expect(publicDelete.status).toBe(405);
    expect(previewIdeas.status).toBe(404);
    expect(unauthenticatedPrivateIdeas.status).toBe(403);
    expect(unauthenticatedPrivateDelete.status).toBe(403);
  });

  it("serves only the dedicated public page on the public hostname", async () => {
    const env = {
      ASSETS: {
        fetch: async (request: Request) => new Response(new URL(request.url).pathname),
      },
    } as Env;

    const response = await worker.fetch(new Request("https://briefing.jdb-builds.com/"), env);
    expect(response.status).toBe(200);
    expect(await response.text()).toBe("/edition.html");
    expect(response.headers.get("X-Frame-Options")).toBe("DENY");
  });
});
