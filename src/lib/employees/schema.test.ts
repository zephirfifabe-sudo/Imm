import { describe, expect, it } from "vitest";
import { employeeFormSchema } from "./schema";

const base = {
  firstName: "Jean",
  lastName: "Dupont",
  internalCode: "EMP-0001",
};

describe("employeeFormSchema", () => {
  it("accepts the minimal required fields", () => {
    const result = employeeFormSchema.safeParse(base);
    expect(result.success).toBe(true);
  });

  it("rejects a PIN that is not exactly 4 digits", () => {
    const result = employeeFormSchema.safeParse({ ...base, pin: "12" });
    expect(result.success).toBe(false);
  });

  it("accepts a valid 4-digit PIN", () => {
    const result = employeeFormSchema.safeParse({ ...base, pin: "1234" });
    expect(result.success).toBe(true);
  });

  it("treats empty optional fields as undefined", () => {
    const result = employeeFormSchema.safeParse({
      ...base,
      email: "",
      jobTitle: "",
      pin: "",
    });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.email).toBeUndefined();
      expect(result.data.jobTitle).toBeUndefined();
      expect(result.data.pin).toBeUndefined();
    }
  });

  it("rejects a missing internal code", () => {
    const result = employeeFormSchema.safeParse({
      firstName: "Jean",
      lastName: "Dupont",
      internalCode: "",
    });
    expect(result.success).toBe(false);
  });
});
