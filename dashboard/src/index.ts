import express, { Request, Response } from "express";
import cors from "cors";
import axios from "axios";

const app = express();
app.use(cors());
app.use(express.json());

const GATEWAY_URL = process.env.GATEWAY_URL || "http://localhost:8080";
const PORT = parseInt(process.env.DASHBOARD_PORT || "3000", 10);
const LOG_LEVEL = process.env.LOG_LEVEL || "info";

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

app.get("/api/events", async (req: Request, res: Response) => {
  try {
    const params = req.query.type ? `?type=${req.query.type}` : "";
    const resp = await axios.get(`${GATEWAY_URL}/api/events${params}`, {
      timeout: 5000,
    });
    log("info", `Fetched ${resp.data.length} events from gateway`);
    res.json(resp.data);
  } catch (err) {
    log("error", `Failed to fetch events: ${err}`);
    res.status(502).json({ error: "Failed to fetch events from gateway" });
  }
});

app.get("/api/timeline", async (_req: Request, res: Response) => {
  try {
    const resp = await axios.get(`${GATEWAY_URL}/api/events`, {
      timeout: 5000,
    });
    const events: Array<{ timestamp: number; type: string; status: string }> =
      resp.data;

    const buckets: Record<string, number> = {};
    for (const event of events) {
      const date = new Date(event.timestamp * 1000);
      const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")} ${String(date.getHours()).padStart(2, "0")}:00`;
      buckets[key] = (buckets[key] || 0) + 1;
    }

    const timeline = Object.entries(buckets)
      .map(([hour, count]) => ({ hour, count }))
      .sort((a, b) => a.hour.localeCompare(b.hour));

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
