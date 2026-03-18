import { execSync } from 'child_process';
import * as http from 'http';

const RUN_ID = process.env.RUN_ID;
const API_BASE_URL = process.env.API_BASE_URL || 'http://api:8080';
const API_AUTH_TOKEN = process.env.AGENTFLOW_RUNNER_API_TOKEN || process.env.AGENTFLOW_API_TOKEN || '';

async function post(path: string, data: any): Promise<void> {
  if (!RUN_ID || !API_BASE_URL) {
    return;
  }

  const url = new URL(path, API_BASE_URL);
  const body = JSON.stringify(data);

  await new Promise<void>((resolve, reject) => {
    const req = http.request(
      {
        hostname: url.hostname,
        port: url.port || 8080,
        path: url.pathname,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(body),
          ...(API_AUTH_TOKEN ? { Authorization: `Bearer ${API_AUTH_TOKEN}` } : {})
        }
      },
      (res) => {
        if ((res.statusCode || 500) >= 400) {
          console.warn(`[agent] Event post skipped (${res.statusCode})`);
        }
        resolve();
      }
    );

    req.on('error', (err) => {
      console.warn(`[agent] Event post error: ${String(err)}`);
      resolve();
    });
    req.write(body);
    req.end();
  });
}

async function emitEvent(eventType: string, payload: any = {}): Promise<void> {
  await post(`/runs/${RUN_ID}/events`, {
    type: eventType,
    run_id: RUN_ID,
    ts: new Date().toISOString(),
    payload
  });
}

function step(stepName: string) {
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
        await emitEvent('step_error', { name: stepName, error: error?.message || String(error), ms: Date.now() - t0 });
        throw error;
      }
    };
    return descriptor;
  };
}

function createLogger(name: string) {
  return {
    info: (message: string, ...args: any[]) => console.log(`[${name}] ${message}`, ...args),
    warn: (message: string, ...args: any[]) => console.warn(`[${name}] ${message}`, ...args),
    error: (message: string, ...args: any[]) => console.error(`[${name}] ${message}`, ...args),
    debug: (message: string, ...args: any[]) => console.log(`[${name}] [DEBUG] ${message}`, ...args)
  };
}

interface AgentConfig {
  name: string;
  version: string;
}

const config: AgentConfig = {
  name: 'ts-agent-events-v3',
  version: '1.0.0'
};

const log = createLogger('agent');

/**
 * Greet function - demonstrates a step in the agent workflow
 * Now uses @step decorator for automatic event emission
 */
async function greet(): Promise<void> {
  // Emit custom event
  await emitEvent('agent_step', {
    step: 'greet',
    agent_name: config.name,
    agent_version: config.version
  });

  log.info('Hello from TypeScript agent!');
  log.info(`Version: ${config.version}`);
  
  // Demonstrate subprocess execution
  try {
    const result = execSync('echo "subprocess says hi from TypeScript"', { encoding: 'utf-8' });
    log.info(`Subprocess output: ${result.trim()}`);
    
    // Emit subprocess event
    await emitEvent('subprocess_result', {
      command: 'echo',
      output: result.trim(),
      success: true
    });
  } catch (error: any) {
    log.error('Error running subprocess:', error.message);
    await emitEvent('subprocess_error', {
      command: 'echo',
      error: error.message
    });
  }
}

/**
 * Process query - demonstrates a tracked step
 */
async function processQuery(query: string): Promise<string> {
  const t0 = Date.now();
  
  await emitEvent('step_start', { name: 'process_query', query });
  
  try {
    // Simulate some processing
    await new Promise(resolve => setTimeout(resolve, 100));
    const result = `Processed: ${query.toUpperCase()}`;
    
    const ms = Date.now() - t0;
    await emitEvent('step_end', { name: 'process_query', result, ms });
    
    return result;
  } catch (error: any) {
    const ms = Date.now() - t0;
    await emitEvent('step_error', { name: 'process_query', error: error.message, ms });
    throw error;
  }
}

/**
 * Main agent entry point
 */
async function main(): Promise<void> {
  log.info('Starting agent...');
  
  // Emit agent start event
  await emitEvent('agent_started', {
    agent_name: config.name,
    agent_version: config.version,
    language: 'typescript'
  });
  
  try {
    // Execute steps
    await greet();
    
    // Process a sample query
    const query = 'hello world';
    const result = await processQuery(query);
    log.info(`Query result: ${result}`);
    
    // Emit completion event
    await emitEvent('agent_completed', {
      agent_name: config.name,
      status: 'success',
      queries_processed: 1
    });
    
    log.info('Agent completed successfully');
  } catch (error: any) {
    log.error('Fatal error:', error.message);
    
    await emitEvent('agent_failed', {
      agent_name: config.name,
      error: error.message,
      stack: error.stack
    });
    
    process.exit(1);
  }
}

// Run the agent
main().catch(error => {
  console.error(`[${config.name}] Fatal error:`, error);
  process.exit(1);
});
