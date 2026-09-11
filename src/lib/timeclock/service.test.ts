import { describe, expect, it } from "vitest";
import { getValidNextActions, isValidNextAction } from "./service";

describe("getValidNextActions", () => {
  it("only allows clocking in when there is no prior entry", () => {
    expect(getValidNextActions(null)).toEqual(["CLOCK_IN"]);
  });

  it("only allows clocking in after a clock-out", () => {
    expect(getValidNextActions("CLOCK_OUT")).toEqual(["CLOCK_IN"]);
  });

  it("allows starting a break or clocking out after a clock-in", () => {
    expect(getValidNextActions("CLOCK_IN")).toEqual(["BREAK_START", "CLOCK_OUT"]);
  });

  it("only allows ending the break once it has started", () => {
    expect(getValidNextActions("BREAK_START")).toEqual(["BREAK_END"]);
  });

  it("allows starting another break or clocking out after a break ends", () => {
    expect(getValidNextActions("BREAK_END")).toEqual(["BREAK_START", "CLOCK_OUT"]);
  });
});

describe("isValidNextAction", () => {
  it("rejects a double clock-in", () => {
    expect(isValidNextAction("CLOCK_IN", "CLOCK_IN")).toBe(false);
  });

  it("rejects ending a break that never started", () => {
    expect(isValidNextAction("CLOCK_IN", "BREAK_END")).toBe(false);
  });

  it("accepts a legitimate clock-out after a break", () => {
    expect(isValidNextAction("BREAK_END", "CLOCK_OUT")).toBe(true);
  });
});
