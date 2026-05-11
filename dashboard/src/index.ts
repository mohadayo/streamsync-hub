import express, { Request, Response } from "express";
import cors from "cors";
import axios from "axios";

const app = express();
app.use(cors());
app.use(express.json());

const GATEWAY_URL = process.env.GATEWAY_URL || "http://localhost:8080";
const PORT = parseInt(process.env.DASHBOARD_PORT || "3000", 10);
const LOG_LEVEL = process.env.LOG_LEVEL || "info";
const TIMELINE_FETCH_LIMIT = parseInt(
  process.env.TIMELINE_FETCH_LIMIT || "1000",
  10
);
const ALLOWED_BUCKETS = new Set(["hour", "day"]);

function log(level: string, message: string): void {
  if (level === "debug" && LOG_LEVEL !== "debug") return;
  const timestamp = new Date().toISOString();
  console.log(`${timestamp} [${level.toUpperCase()}] dashboard: ${message}`);
}

interface DashboardSnapshot {
  gateway_stats: Record<string, unknown> | null;
  generated_at: string;
  service: string;
}

app.get("/health", (_req: Request, res: Response) => {
  res.json({
    status: "healthy",
    service: "dashboard",
    timestamp: Date.now() / 1000,
  });
});

app.get("/api/dashboard", async (_req: Request, res: Response) => {
  const snapshot: DashboardSnapshot = {
    gateway_stats: null,
    generated_at: new Date().toISOString(),
    service: "dashboard",
  };

  try {
    const statsResp = await axios.get(`${GATEWAY_URL}/api/stats`, {
      timeout: 5000,
    });
    snapshot.gateway_stats = statsResp.data;
    log("info", "Fetched gateway stats successfully");
  } catch (err) {
    log("error", `Failed to fetch gateway stats: ${err}`);
    snapshot.gateway_stats = { error: "Gateway unreachable" };
  }

  res.json(snapshot);
});

app.get("/api/stats", async (req: Request, res: Response) => {
  try {
    const params = new URLSearchParams();
    if (req.query.type) params.set("type", String(req.query.type));
    if (req.query.status) params.set("status", String(req.query.status));
    if (req.query.since) params.set("since", String(req.query.since));
    if (req.query.until) params.set("until", String(req.query.until));
    const qs = params.toString();
    const url = qs ? `${GATEWAY_URL}/api/stats?${qs}` : `${GATEWAY_URL}/api/stats`;
    const resp = await axios.get(url, { timeout: 5000 });
    log("info", `Fetched stats from gateway (total: ${resp.data.total})`);
    res.json(resp.data);
  } catch (err) {
    const e = err as { response?: { status: number; data: unknown } };
    if (e.response && e.response.status >= 400 && e.response.status < 500) {
      log("warn", `Gateway rejected stats request: ${e.response.status}`);
      res.status(e.response.status).json(e.response.data);
      return;
    }
    log("error", `Failed to fetch stats: ${err}`);
    res.status(502).json({ error: "Failed to fetch stats from gateway" });
  }
});

app.get("/api/events", async (req: Request, res: Response) => {
  try {
    const params = new URLSearchParams();
    if (req.query.type) params.set("type", String(req.query.type));
    if (req.query.status) params.set("status", String(req.query.status));
    if (req.query.limit) params.set("limit", String(req.query.limit));
    if (req.query.offset) params.set("offset", String(req.query.offset));
    const qs = params.toString();
    const url = qs ? `${GATEWAY_URL}/api/events?${qs}` : `${GATEWAY_URL}/api/events`;
    const resp = await axios.get(url, { timeout: 5000 });
    log("info", `Fetched events from gateway (total: ${resp.data.total})`);
    res.json(resp.data);
  } catch (err) {
    log("error", `Failed to fetch events: ${err}`);
    res.status(502).json({ error: "Failed to fetch events from gateway" });
  }
});

function bucketKey(date: Date, bucket: string): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  if (bucket === "day") {
    return `${y}-${m}-${d}`;
  }
  const h = String(date.getHours()).padStart(2, "0");
  return `${y}-${m}-${d} ${h}:00`;
}

app.get("/api/timeline", async (req: Request, res: Response) => {
  const bucket = req.query.bucket ? String(req.query.bucket) : "hour";
  if (!ALLOWED_BUCKETS.has(bucket)) {
    res.status(400).json({
      error: "Invalid bucket",
      allowed: Array.from(ALLOWED_BUCKETS).sort(),
    });
    return;
  }

  try {
    const params = new URLSearchParams();
    if (req.query.type) params.set("type", String(req.query.type));
    if (req.query.status) params.set("status", String(req.query.status));
    if (req.query.since) params.set("since", String(req.query.since));
    if (req.query.until) params.set("until", String(req.query.until));
    params.set("limit", String(TIMELINE_FETCH_LIMIT));
    const url = `${GATEWAY_URL}/api/events?${params.toString()}`;
    const resp = await axios.get(url, { timeout: 5000 });
    const events: Array<{ timestamp: number; type: string; status: string }> =
      resp.data.events || [];

    const buckets: Record<string, number> = {};
    for (const event of events) {
      const date = new Date(event.timestamp * 1000);
      const key = bucketKey(date, bucket);
      buckets[key] = (buckets[key] || 0) + 1;
    }

    const timeline = Object.entries(buckets)
      .map(([slot, count]) => ({ [bucket]: slot, count }))
      .sort((a, b) =>
        String(a[bucket as keyof typeof a]).localeCompare(
          String(b[bucket as keyof typeof b])
        )
      );

    res.json(timeline);
  } catch (err) {
    log("error", `Failed to build timeline: ${err}`);
    res.status(502).json({ error: "Failed to build timeline" });
  }
});

export function createApp(): express.Application {
  return app;
}

if (require.main === module) {
  app.listen(PORT, "0.0.0.0", () => {
    log("info", `Starting dashboard on port ${PORT}`);
  });
}

export default app;
