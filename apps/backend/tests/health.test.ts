import { describe, expect, it } from "vitest";
import request from "supertest";
import { app } from "../src/app";

describe("GET /health", () => {
  it("répond 200 avec status ok", async () => {
    const response = await request(app).get("/health");
    expect(response.status).toBe(200);
    expect(response.body).toEqual({ status: "ok" });
  });
});

describe("Routes protégées", () => {
  it("refuse l'accès sans token", async () => {
    const response = await request(app).get("/api/analyses");
    expect(response.status).toBe(401);
  });

  it("valide le corps de la requête d'inscription", async () => {
    const response = await request(app).post("/api/auth/register").send({ email: "invalide" });
    expect(response.status).toBe(400);
  });
});
