import { describe, expect, it } from "vitest";
import { rowsToCsv } from "./csv";
import type { ExportRow } from "./rows";

function row(overrides: Partial<ExportRow> = {}): ExportRow {
  return {
    employee: "Jean Dupont",
    date: "2026-09-07",
    workedHm: "7h43",
    workedDecimal: "7.72",
    breakHm: "0h46",
    anomalies: "",
    ...overrides,
  };
}

describe("rowsToCsv", () => {
  it("starts with a UTF-8 BOM", () => {
    expect(rowsToCsv([])).toMatch(/^﻿/);
  });

  it("uses a semicolon delimiter (Belgian/French Excel default)", () => {
    const csv = rowsToCsv([row()]);
    const lines = csv.replace(/^﻿/, "").split("\r\n");
    expect(lines[1]).toBe("Jean Dupont;2026-09-07;7h43;7.72;0h46;");
  });

  it("quotes a field containing the delimiter", () => {
    const csv = rowsToCsv([row({ employee: "Dupont; Jean" })]);
    const lines = csv.replace(/^﻿/, "").split("\r\n");
    expect(lines[1]).toContain('"Dupont; Jean"');
  });

  it("doubles internal quotes", () => {
    const csv = rowsToCsv([row({ anomalies: 'Il a dit "en retard"' })]);
    const lines = csv.replace(/^﻿/, "").split("\r\n");
    expect(lines[1]).toContain('"Il a dit ""en retard"""');
  });

  it("quotes a field containing a newline", () => {
    const csv = rowsToCsv([row({ anomalies: "ligne 1\nligne 2" })]);
    expect(csv).toContain('"ligne 1\nligne 2"');
  });

  it("leaves a clean field unquoted", () => {
    const csv = rowsToCsv([row()]);
    const lines = csv.replace(/^﻿/, "").split("\r\n");
    expect(lines[1]).not.toContain('"');
  });

  it("includes the header row with the delimiter", () => {
    const csv = rowsToCsv([]);
    const header = csv.replace(/^﻿/, "");
    expect(header).toBe("Employé;Date;Temps travaillé (h:min);Temps travaillé (décimal);Pause;Anomalies");
  });
});
