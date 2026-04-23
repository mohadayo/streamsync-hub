import request from "supertest";
import app from "./index";

describe("Dashboard Service", () => {
  describe("GET /health", () => {
    it("should return healthy status", async () => {
      const res = await request(app).get("/health");
      expect(res.status).toBe(200);
      expect(res.body.status).toBe("healthy");
      expect(res.body.service).toBe("dashboard");
      expect(res.body.timestamp).toBeDefined();
    });
  });

  describe("GET /api/dashboard", () => {
    it("should return a dashboard snapshot", async () => {
      const res = await request(app).get("/api/dashboard");
      expect(res.status).toBe(200);
      expect(res.body.service).toBe("dashboard");
      expect(res.body.generated_at).toBeDefined();
      expect(res.body.gateway_stats).toBeDefined();
    });
  });

  describe("GET /api/events", () => {
    it("should return 502 when gateway is unreachable", async () => {
      const res = await request(app).get("/api/events");
      expect(res.status).toBe(502);
      expect(res.body.error).toBeDefined();
    });
  });

  describe("GET /api/timeline", () => {
    it("should return 502 when gateway is unreachable", async () => {
      const res = await request(app).get("/api/timeline");
      expect(res.status).toBe(502);
      expect(res.body.error).toBeDefined();
    });
  });
});
