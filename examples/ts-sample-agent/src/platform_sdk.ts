/**
 * AgentFlow Platform SDK for TypeScript/Node.js agents
 * 
 * Provides event emission and logging capabilities similar to the Python SDK.
 * Events are sent to the platform API for structured telemetry tracking.
 */

import * as http from 'http';

const RUN_ID = process.env.RUN_ID;
// Inside the Docker network the API listens on port 8000 (not the host-mapped 8080).
const API_BASE_URL = process.env.API_BASE_URL || 'http://api:8000';
const API_AUTH_TOKEN = process.env.AGENTFLOW_RUNNER_API_TOKEN || process.env.AGENTFLOW_API_TOKEN || '';

/**
 * Post data to the platform API
 */
async function post(path: string, data: any): Promise<void> {
  if (!RUN_ID || !API_BASE_URL) {
    console.error('[PLATFORM_SDK] Skipping event post: RUN_ID or API_BASE_URL not set');
    return;
  }

  const url = new URL(path, API_BASE_URL);
  const body = JSON.stringify(data);

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

    const req = http.request(options, (res) => {
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
 * Emit a structured event to the platform
 * 
 * Events are automatically categorized and displayed in the platform UI.
 * 
 * @param eventType - Type of event (e.g., 'step_start', 'query_processed', 'agent_started')
 * @param payload - Event data object
 * 
 * @example
 * ```typescript
 * await emitEvent('agent_started', {
 *   model: 'gpt-4',
 *   tools: ['search', 'calculator']
 * });
 * 
 * await emitEvent('query_processed', {
 *   query: 'What is 2+2?',
 *   steps: 3,
 *   duration_ms: 1250
 * });
 * ```
 */
export async function emitEvent(eventType: string, payload: any = {}): Promise<void> {
  const event = {
    type: eventType,
    run_id: RUN_ID,
    ts: new Date().toISOString(),
    payload
  };

  await post(`/runs/${RUN_ID}/events`, event).catch((err) => {
    // Event posting is best-effort — never let it crash the agent.
    console.error(`[agent] Event post error: ${err.message || err}`);
  });
}

/**
 * Decorator for tracking function execution as steps
 * 
 * Automatically emits step_start and step_end events with timing information.
 * 
 * @param stepName - Name of the step for tracking
 * 
 * @example
 * ```typescript
 * class Agent {
 *   @step('initialize')
 *   async initialize() {
 *     // Setup code...
 *   }
 * 
 *   @step('process_query')
 *   async processQuery(query: string) {
 *     // Processing logic...
 *     return result;
 *   }
 * }
 * ```
 */
export function step(stepName: string) {
  return function (target: any, propertyKey: string, descriptor: PropertyDescriptor) {
    const originalMethod = descriptor.value;

    descriptor.value = async function (...args: any[]) {
      const t0 = Date.now();
      await emitEvent('step_start', { name: stepName });

      try {
        const result = await originalMethod.apply(this, args);
        const ms = Date.now() - t0;
        await emitEvent('step_end', { name: stepName, ms });
        return result;
      } catch (error: any) {
        const ms = Date.now() - t0;
        await emitEvent('step_error', {
          name: stepName,
          error: error.message || String(error),
          ms
        });
        throw error;
      }
    };

    return descriptor;
  };
}

/**
 * Simple logger that logs to console and optionally posts to platform
 * 
 * @example
 * ```typescript
 * const log = createLogger('agent');
 * log.info('Starting agent execution');
 * log.warn('Deprecated feature used');
 * log.error('Failed to process query', error);
 * ```
 */
export interface Logger {
  info(message: string, ...args: any[]): void;
  warn(message: string, ...args: any[]): void;
  error(message: string, ...args: any[]): void;
  debug(message: string, ...args: any[]): void;
}

export function createLogger(name: string = 'agent'): Logger {
  return {
    info: (message: string, ...args: any[]) => {
      console.log(`[${name}] ${message}`, ...args);
    },
    warn: (message: string, ...args: any[]) => {
      console.warn(`[${name}] ${message}`, ...args);
    },
    error: (message: string, ...args: any[]) => {
      console.error(`[${name}] ${message}`, ...args);
    },
    debug: (message: string, ...args: any[]) => {
      console.log(`[${name}] [DEBUG] ${message}`, ...args);
    }
  };
}

/**
 * Initialize the platform SDK (called automatically if using sitecustomize equivalent)
 * 
 * Emits a runner_boot event to signal agent startup.
 */
export async function initialize(): Promise<void> {
  await emitEvent('runner_boot', {
    runtime: 'node.js',
    version: process.version,
    platform: process.platform
  });
}

// Auto-initialize if RUN_ID is set (running in platform context)
if (RUN_ID) {
  initialize().catch((err) => {
    console.error('[PLATFORM_SDK] Failed to initialize:', err);
  });
}
