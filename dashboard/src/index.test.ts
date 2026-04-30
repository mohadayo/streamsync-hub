import request from "supertest";
import axios from "axios";
import app from "./index";

jest.mock("axios");
const mockedAxios = axios as jest.Mocked<typeof axios>;

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
      mockedAxios.get.mockResolvedValueOnce({
        data: { total: 5, by_status: {}, by_type: {} },
        status: 200,
        statusText: "OK",
        headers: {},
        config: {} as never,
      });
      const res = await request(app).get("/api/dashboard");
      expect(res.status).toBe(200);
      expect(res.body.service).toBe("dashboard");
      expect(res.body.generated_at).toBeDefined();
      expect(res.body.gateway_stats).toBeDefined();
    });

    it("should handle gateway unreachable", async () => {
      mockedAxios.get.mockRejectedValueOnce(new Error("ECONNREFUSED"));
      const res = await request(app).get("/api/dashboard");
      expect(res.status).toBe(200);
      expect(res.body.gateway_stats).toEqual({ error: "Gateway unreachable" });
    });
  });

  describe("GET /api/events", () => {
    it("should proxy events from gateway", async () => {
      mockedAxios.get.mockResolvedValueOnce({
        data: { events: [{ type: "test" }], total: 1, limit: 50, offset: 0 },
        status: 200,
        statusText: "OK",
        headers: {},
        config: {} as never,
      });
      const res = await request(app).get("/api/events");
      expect(res.status).toBe(200);
      expect(res.body.events).toHaveLength(1);
      expect(res.body.total).toBe(1);
    });

    it("should forward type query parameter", async () => {
      mockedAxios.get.mockResolvedValueOnce({
        data: { events: [], total: 0, limit: 50, offset: 0 },
        status: 200,
        statusText: "OK",
        headers: {},
        config: {} as never,
      });
      await request(app).get("/api/events?type=user.signup");
      expect(mockedAxios.get).toHaveBeenCalledWith(
        expect.stringContaining("type=user.signup"),
        expect.any(Object)
      );
    });

    it("should forward limit and offset query parameters", async () => {
      mockedAxios.get.mockResolvedValueOnce({
        data: { events: [], total: 0, limit: 10, offset: 5 },
        status: 200,
        statusText: "OK",
        headers: {},
        config: {} as never,
      });
      await request(app).get("/api/events?limit=10&offset=5");
      const calledUrl = mockedAxios.get.mock.calls[mockedAxios.get.mock.calls.length - 1][0];
      expect(calledUrl).toContain("limit=10");
      expect(calledUrl).toContain("offset=5");
    });

    it("should return 502 when gateway is unreachable", async () => {
      mockedAxios.get.mockRejectedValueOnce(new Error("ECONNREFUSED"));
      const res = await request(app).get("/api/events");
      expect(res.status).toBe(502);
      expect(res.body.error).toBeDefined();
    });
  });

  describe("GET /api/timeline", () => {
    it("should build timeline from gateway events", async () => {
      const now = Date.now() / 1000;
      mockedAxios.get.mockResolvedValueOnce({
        data: {
          events: [
            { timestamp: now, type: "test", status: "received" },
            { timestamp: now, type: "test", status: "received" },
          ],
          total: 2,
          limit: 50,
          offset: 0,
        },
        status: 200,
        statusText: "OK",
        headers: {},
        config: {} as never,
      });
      const res = await request(app).get("/api/timeline");
      expect(res.status).toBe(200);
      expect(Array.isArray(res.body)).toBe(true);
      expect(res.body[0]).toHaveProperty("hour");
      expect(res.body[0]).toHaveProperty("count");
      expect(res.body[0].count).toBe(2);
    });

    it("should return 502 when gateway is unreachable", async () => {
      mockedAxios.get.mockRejectedValueOnce(new Error("ECONNREFUSED"));
      const res = await request(app).get("/api/timeline");
      expect(res.status).toBe(502);
      expect(res.body.error).toBeDefined();
    });
  });
});
