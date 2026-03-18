/**
 * AgentFlow Platform SDK for TypeScript/Node.js agents (local deployment)
 *
 * Identical to the container SDK except the default API base URL points to
 * the host-mapped port (8080) so agents running on the local machine can reach
 * the API without being inside the Docker network.
 *
 * Override with API_BASE_URL environment variable for any other target.
 */

import * as http from 'http';
import * as https from 'https';

const RUN_ID = process.env.RUN_ID;
// Local agents run on the host — the API is reachable via the forwarded port.
const API_BASE_URL = process.env.API_BASE_URL || 'http://localhost:8080';
const API_AUTH_TOKEN = process.env.AGENTFLOW_RUNNER_API_TOKEN || process.env.AGENTFLOW_API_TOKEN || '';

/**
 * Post data to the platform API.
 */
async function post(path: string, data: any): Promise<void> {
  if (!RUN_ID || !API_BASE_URL) {
    console.error('[PLATFORM_SDK] Skipping event post: RUN_ID or API_BASE_URL not set');
    return;
  }

  const url = new URL(path, API_BASE_URL);
  const body = JSON.stringify(data);
  const transport = url.protocol === 'https:' ? https : http;

  return new Promise((resolve, reject) => {
    const options = {
      hostname: url.hostname,
      port: url.port ? parseInt(url.port, 10) : (url.protocol === 'https:' ? 443 : 80),
      path: url.pathname,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(body),
        ...(API_AUTH_TOKEN ? { 'Authorization': `Bearer ${API_AUTH_TOKEN}` } : {})
      }
    };

    const req = transport.request(options, (res) => {
      console.error(`[PLATFORM_SDK] Posted event to ${url.pathname}: ${res.statusCode}`);
      resolve();
    });

    req.on('error', (error) => {
      console.error(`[PLATFORM_SDK] Failed to post event to ${url.pathname}:`, error.message);
      reject(error);
    });

    req.write(body);
    req.end();
  });
}

/**
 * Emit a structured event to the platform.
 *
 * Event posting is best-effort — errors are logged and never crash the agent.
 *
 * @param eventType - Type identifier (e.g. 'step_start', 'query_processed')
 * @param payload   - Arbitrary event data
 */
export async function emitEvent(eventType: string, payload: any = {}): Promise<void> {
  const event = {
    type: eventType,
    run_id: RUN_ID,
    ts: new Date().toISOString(),
    payload
  };

  await post(`/runs/${RUN_ID}/events`, event).catch((err) => {
    console.error(`[agent] Event post error: ${err.message || err}`);
  });
}

/**
 * Decorator for tracking function execution as named steps.
 *
 * Automatically emits step_start, step_end, and step_error events with timing.
 *
 * @param stepName - Display name of the step
 */
export function step(stepName: string) {
  return function (_target: any, _propertyKey: string, descriptor: PropertyDescriptor) {
    const originalMethod = descriptor.value;

    descriptor.value = async function (...args: any[]) {
      const t0 = Date.now();
      await emitEvent('step_start', { name: stepName });

      try {
        const result = await originalMethod.apply(this, args);
        await emitEvent('step_end', { name: stepName, ms: Date.now() - t0 });
        return result;
      } catch (error: any) {
        await emitEvent('step_error', {
          name: stepName,
          error: error.message || String(error),
          ms: Date.now() - t0
        });
        throw error;
      }
    };

    return descriptor;
  };
}

/**
 * Simple structured logger that writes to stdout/stderr.
 */
export interface Logger {
  info(message: string, ...args: any[]): void;
  warn(message: string, ...args: any[]): void;
  error(message: string, ...args: any[]): void;
  debug(message: string, ...args: any[]): void;
}

export function createLogger(name: string = 'agent'): Logger {
  return {
    info:  (msg, ...a) => console.log(`[${name}] ${msg}`, ...a),
    warn:  (msg, ...a) => console.warn(`[${name}] ${msg}`, ...a),
    error: (msg, ...a) => console.error(`[${name}] ${msg}`, ...a),
    debug: (msg, ...a) => console.log(`[${name}] [DEBUG] ${msg}`, ...a)
  };
}

/**
 * Emit a runner_boot event to signal agent startup.
 */
export async function initialize(): Promise<void> {
  await emitEvent('runner_boot', {
    runtime: 'node.js',
    version: process.version,
    platform: process.platform,
    deployment: 'local'
  });
}

// Auto-initialize when running inside the platform (RUN_ID is injected by the worker).
if (RUN_ID) {
  initialize().catch((err) => {
    console.error('[PLATFORM_SDK] Failed to initialize:', err);
  });
}
