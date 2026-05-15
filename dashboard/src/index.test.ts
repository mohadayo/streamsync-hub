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

  describe("GET /api/stats", () => {
    it("should proxy stats from gateway", async () => {
      mockedAxios.get.mockResolvedValueOnce({
        data: { total: 3, by_status: { received: 3 }, by_type: { x: 3 } },
        status: 200,
        statusText: "OK",
        headers: {},
        config: {} as never,
      });
      const res = await request(app).get("/api/stats");
      expect(res.status).toBe(200);
      expect(res.body.total).toBe(3);
      expect(res.body.by_type).toEqual({ x: 3 });
    });

    it("should forward type/status/since/until filters to gateway", async () => {
      mockedAxios.get.mockResolvedValueOnce({
        data: { total: 0, by_status: {}, by_type: {} },
        status: 200,
        statusText: "OK",
        headers: {},
        config: {} as never,
      });
      await request(app).get(
        "/api/stats?type=user.signup&status=processed&since=100&until=200"
      );
      const calledUrl = mockedAxios.get.mock.calls[mockedAxios.get.mock.calls.length - 1][0];
      expect(calledUrl).toContain("type=user.signup");
      expect(calledUrl).toContain("status=processed");
      expect(calledUrl).toContain("since=100");
      expect(calledUrl).toContain("until=200");
    });

    it("should propagate 4xx errors from gateway", async () => {
      mockedAxios.get.mockRejectedValueOnce({
        response: { status: 400, data: { error: "Invalid status" } },
      });
      const res = await request(app).get("/api/stats?status=bogus");
      expect(res.status).toBe(400);
      expect(res.body.error).toBe("Invalid status");
    });

    it("should return 502 when gateway is unreachable", async () => {
      mockedAxios.get.mockRejectedValueOnce(new Error("ECONNREFUSED"));
      const res = await request(app).get("/api/stats");
      expect(res.status).toBe(502);
      expect(res.body.error).toBeDefined();
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

    it("should forward status query parameter", async () => {
      mockedAxios.get.mockResolvedValueOnce({
        data: { events: [], total: 0, limit: 50, offset: 0 },
        status: 200,
        statusText: "OK",
        headers: {},
        config: {} as never,
      });
      await request(app).get("/api/events?status=process_failed");
      const calledUrl = mockedAxios.get.mock.calls[mockedAxios.get.mock.calls.length - 1][0];
      expect(calledUrl).toContain("status=process_failed");
    });

    it("should forward since/until filters to gateway", async () => {
      mockedAxios.get.mockResolvedValueOnce({
        data: { events: [], total: 0, limit: 50, offset: 0 },
        status: 200,
        statusText: "OK",
        headers: {},
        config: {} as never,
      });
      await request(app).get("/api/events?since=1700000000&until=1800000000");
      const calledUrl = mockedAxios.get.mock.calls[mockedAxios.get.mock.calls.length - 1][0];
      expect(calledUrl).toContain("since=1700000000");
      expect(calledUrl).toContain("until=1800000000");
    });

    it("should forward sort and order parameters to gateway", async () => {
      mockedAxios.get.mockResolvedValueOnce({
        data: { events: [], total: 0, limit: 50, offset: 0, sort: "timestamp", order: "desc" },
        status: 200,
        statusText: "OK",
        headers: {},
        config: {} as never,
      });
      await request(app).get("/api/events?sort=type&order=desc");
      const calledUrl = mockedAxios.get.mock.calls[mockedAxios.get.mock.calls.length - 1][0];
      expect(calledUrl).toContain("sort=type");
      expect(calledUrl).toContain("order=desc");
    });

    it("should propagate 4xx errors from gateway", async () => {
      mockedAxios.get.mockRejectedValueOnce({
        response: { status: 400, data: { error: "Invalid sort field" } },
      });
      const res = await request(app).get("/api/events?sort=bogus");
      expect(res.status).toBe(400);
      expect(res.body.error).toBe("Invalid sort field");
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

    it("should pass a high limit to gateway when fetching events", async () => {
      mockedAxios.get.mockResolvedValueOnce({
        data: { events: [], total: 0, limit: 1000, offset: 0 },
        status: 200,
        statusText: "OK",
        headers: {},
        config: {} as never,
      });
      await request(app).get("/api/timeline");
      const calledUrl = mockedAxios.get.mock.calls[mockedAxios.get.mock.calls.length - 1][0];
      expect(calledUrl).toContain("limit=1000");
    });

    it("should forward type/status/since/until filters to gateway", async () => {
      mockedAxios.get.mockResolvedValueOnce({
        data: { events: [], total: 0, limit: 1000, offset: 0 },
        status: 200,
        statusText: "OK",
        headers: {},
        config: {} as never,
      });
      await request(app).get(
        "/api/timeline?type=user.signup&status=processed&since=1700000000&until=1800000000"
      );
      const calledUrl = mockedAxios.get.mock.calls[mockedAxios.get.mock.calls.length - 1][0];
      expect(calledUrl).toContain("type=user.signup");
      expect(calledUrl).toContain("status=processed");
      expect(calledUrl).toContain("since=1700000000");
      expect(calledUrl).toContain("until=1800000000");
    });

    it("should aggregate by day when bucket=day", async () => {
      const t1 = new Date(2026, 0, 1, 3, 30).getTime() / 1000;
      const t2 = new Date(2026, 0, 1, 18, 45).getTime() / 1000;
      const t3 = new Date(2026, 0, 2, 10, 0).getTime() / 1000;
      mockedAxios.get.mockResolvedValueOnce({
        data: {
          events: [
            { timestamp: t1, type: "x", status: "received" },
            { timestamp: t2, type: "x", status: "received" },
            { timestamp: t3, type: "x", status: "received" },
          ],
          total: 3,
          limit: 1000,
          offset: 0,
        },
        status: 200,
        statusText: "OK",
        headers: {},
        config: {} as never,
      });
      const res = await request(app).get("/api/timeline?bucket=day");
      expect(res.status).toBe(200);
      expect(res.body).toHaveLength(2);
      expect(res.body[0]).toHaveProperty("day");
      expect(res.body[0].count).toBe(2);
      expect(res.body[1].count).toBe(1);
    });

    it("should reject invalid bucket values", async () => {
      const res = await request(app).get("/api/timeline?bucket=week");
      expect(res.status).toBe(400);
      expect(res.body.error).toBe("Invalid bucket");
      expect(res.body.allowed).toEqual(["day", "hour"]);
    });

    it("should return 502 when gateway is unreachable", async () => {
      mockedAxios.get.mockRejectedValueOnce(new Error("ECONNREFUSED"));
      const res = await request(app).get("/api/timeline");
      expect(res.status).toBe(502);
      expect(res.body.error).toBeDefined();
    });
  });
});
