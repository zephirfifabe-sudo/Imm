import { describe, expect, it } from "vitest";
import {
  getIdentificationProvider,
  pinProvider,
  qrProvider,
  nfcProvider,
} from "./identification-providers";

describe("getIdentificationProvider", () => {
  it("resolves each method to its own provider", () => {
    expect(getIdentificationProvider("PIN")).toBe(pinProvider);
    expect(getIdentificationProvider("QR")).toBe(qrProvider);
    expect(getIdentificationProvider("NFC")).toBe(nfcProvider);
  });
});

describe("pinProvider.isValidInput", () => {
  it("accepts a 4-digit PIN", () => {
    expect(pinProvider.isValidInput("1234")).toBe(true);
  });

  it("rejects anything else", () => {
    expect(pinProvider.isValidInput("12")).toBe(false);
    expect(pinProvider.isValidInput("abcd")).toBe(false);
    expect(pinProvider.isValidInput("")).toBe(false);
  });
});

describe("qrProvider.isValidInput / nfcProvider.isValidInput", () => {
  it("accept any non-empty token", () => {
    expect(qrProvider.isValidInput("some-token")).toBe(true);
    expect(nfcProvider.isValidInput("04:a2:b3:c4")).toBe(true);
  });

  it("reject an empty or blank value", () => {
    expect(qrProvider.isValidInput("")).toBe(false);
    expect(qrProvider.isValidInput("   ")).toBe(false);
    expect(nfcProvider.isValidInput("")).toBe(false);
  });
});
