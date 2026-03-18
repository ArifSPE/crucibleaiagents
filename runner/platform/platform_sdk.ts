import * as http from "http";

const RUN_ID = process.env.RUN_ID;
const API_BASE_URL = process.env.API_BASE_URL || "http://api:8080";
const API_AUTH_TOKEN = process.env.AGENTFLOW_RUNNER_API_TOKEN || process.env.AGENTFLOW_API_TOKEN || "";

async function post(path: string, data: any): Promise<void> {
  if (!RUN_ID || !API_BASE_URL) return;

  const url = new URL(path, API_BASE_URL);
  const body = JSON.stringify(data);

  return new Promise((resolve, reject) => {
    const options = {
      hostname: url.hostname,
      port: url.port || 8080,
      path: url.pathname,
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Content-Length": Buffer.byteLength(body),
        ...(API_AUTH_TOKEN ? { Authorization: `Bearer ${API_AUTH_TOKEN}` } : {}),
      },
    };

    const req = http.request(options, (res) => {
      if ((res.statusCode || 500) >= 400) {
        reject(new Error(`event post failed: ${res.statusCode}`));
        return;
      }
      resolve();
    });

    req.on("error", reject);
    req.write(body);
    req.end();
  });
}

export async function emitEvent(eventType: string, payload: any = {}): Promise<void> {
  const event = {
    type: eventType,
    run_id: RUN_ID,
    ts: new Date().toISOString(),
    payload,
  };
  await post(`/runs/${RUN_ID}/events`, event);
}

export function createLogger(name: string = "agent") {
  return {
    info: (m: string, ...a: any[]) => console.log(`[${name}] ${m}`, ...a),
    warn: (m: string, ...a: any[]) => console.warn(`[${name}] ${m}`, ...a),
    error: (m: string, ...a: any[]) => console.error(`[${name}] ${m}`, ...a),
    debug: (m: string, ...a: any[]) => console.log(`[${name}] [DEBUG] ${m}`, ...a),
  };
}
