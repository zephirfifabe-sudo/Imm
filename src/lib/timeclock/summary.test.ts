import { describe, expect, it } from "vitest";
import { summarizeDay, getPresenceState, type SummaryEntry } from "./summary";

function entry(type: SummaryEntry["type"], time: string): SummaryEntry {
  return { type, occurred_at: `2026-09-07T${time}:00.000Z` };
}

describe("summarizeDay", () => {
  it("computes a full day with one break, matching the spec example", () => {
    const entries = [
      entry("CLOCK_IN", "09:02"),
      entry("BREAK_START", "12:01"),
      entry("BREAK_END", "12:47"),
      entry("CLOCK_OUT", "17:31"),
    ];

    const result = summarizeDay(entries, { isPastDay: true });

    // 09:02 -> 17:31 = 8h29 worked total, minus 46 min break = 7h43 (463 min)
    expect(result.workedMinutes).toBe(463);
    expect(result.breakMinutes).toBe(46);
    expect(result.anomalies).toEqual([]);
  });

  it("computes a day with no break", () => {
    const entries = [entry("CLOCK_IN", "09:00"), entry("CLOCK_OUT", "17:00")];
    const result = summarizeDay(entries, { isPastDay: true });
    expect(result.workedMinutes).toBe(480);
    expect(result.breakMinutes).toBe(0);
    expect(result.anomalies).toEqual([]);
  });

  it("flags an open day (clocked in, never clocked out) only when in the past", () => {
    const entries = [entry("CLOCK_IN", "09:00")];

    expect(summarizeDay(entries, { isPastDay: true }).anomalies).toEqual([
      "OPEN_DAY",
    ]);
    expect(summarizeDay(entries, { isPastDay: false }).anomalies).toEqual([]);
  });

  it("flags a clock-out with no prior clock-in", () => {
    const entries = [entry("CLOCK_OUT", "17:00")];
    const result = summarizeDay(entries, { isPastDay: true });
    expect(result.anomalies).toEqual(["CLOCK_OUT_WITHOUT_CLOCK_IN"]);
    expect(result.workedMinutes).toBe(0);
  });

  it("flags an unclosed break as an open day", () => {
    const entries = [entry("CLOCK_IN", "09:00"), entry("BREAK_START", "12:00")];
    const result = summarizeDay(entries, { isPastDay: true });
    expect(result.anomalies).toEqual(["OPEN_DAY"]);
  });

  it("ignores entry order in the input array", () => {
    const entries = [
      entry("CLOCK_OUT", "17:00"),
      entry("CLOCK_IN", "09:00"),
    ];
    const result = summarizeDay(entries, { isPastDay: true });
    expect(result.workedMinutes).toBe(480);
    expect(result.anomalies).toEqual([]);
  });
});

describe("getPresenceState", () => {
  it("is absent with no prior entry", () => {
    expect(getPresenceState(null)).toBe("ABSENT");
  });

  it("is present after clocking in", () => {
    expect(getPresenceState("CLOCK_IN")).toBe("PRESENT");
  });

  it("is on break after a break starts", () => {
    expect(getPresenceState("BREAK_START")).toBe("ON_BREAK");
  });

  it("is present again after a break ends", () => {
    expect(getPresenceState("BREAK_END")).toBe("PRESENT");
  });

  it("is absent after clocking out", () => {
    expect(getPresenceState("CLOCK_OUT")).toBe("ABSENT");
  });
});
