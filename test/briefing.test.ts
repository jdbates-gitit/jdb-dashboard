import { describe, expect, it } from "vitest";
import { extractOutputText, sanitizeGeneratedBriefing } from "../src/briefing";
import { localDate, localHour } from "../src/index";

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
});
