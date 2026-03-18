import { execSync } from 'child_process';
import { emitEvent, createLogger } from './platform_sdk.ts';

const AGENT_NAME = 'local-ts-sample-agent';
const AGENT_VERSION = '1.0.0';

const log = createLogger(AGENT_NAME);

/**
 * Greet step — logs a greeting and demonstrates subprocess execution.
 */
async function greet(): Promise<void> {
  await emitEvent('step_start', { name: 'greet' });
  const t0 = Date.now();

  try {
    log.info('Hello from local TypeScript agent!');
    log.info(`Version: ${AGENT_VERSION}`);

    const result = execSync('echo "subprocess says hi from local agent"', { encoding: 'utf-8' });
    log.info(`Subprocess output: ${result.trim()}`);

    await emitEvent('subprocess_result', {
      command: 'echo',
      output: result.trim(),
      success: true
    });

    await emitEvent('step_end', { name: 'greet', ms: Date.now() - t0 });
  } catch (error: any) {
    log.error('Error in greet step:', error.message);
    await emitEvent('step_error', { name: 'greet', error: error.message, ms: Date.now() - t0 });
    throw error;
  }
}

/**
 * Process query step — simulates some work and returns a result.
 */
async function processQuery(query: string): Promise<string> {
  await emitEvent('step_start', { name: 'process_query', query });
  const t0 = Date.now();

  try {
    // Simulate processing delay
    await new Promise(resolve => setTimeout(resolve, 100));
    const result = `Processed (local): ${query.toUpperCase()}`;

    await emitEvent('step_end', { name: 'process_query', result, ms: Date.now() - t0 });
    return result;
  } catch (error: any) {
    await emitEvent('step_error', { name: 'process_query', error: error.message, ms: Date.now() - t0 });
    throw error;
  }
}

/**
 * Main agent entry point.
 */
async function main(): Promise<void> {
  log.info('Starting agent...');

  await emitEvent('agent_started', {
    agent_name: AGENT_NAME,
    agent_version: AGENT_VERSION,
    language: 'typescript',
    deployment: 'local'
  });

  try {
    await greet();

    const query = 'hello from local deployment';
    const result = await processQuery(query);
    log.info(`Query result: ${result}`);

    await emitEvent('agent_completed', {
      agent_name: AGENT_NAME,
      status: 'success',
      queries_processed: 1
    });

    log.info('Agent completed successfully');
  } catch (error: any) {
    log.error('Fatal error:', error.message);

    await emitEvent('agent_failed', {
      agent_name: AGENT_NAME,
      error: error.message,
      stack: error.stack
    });

    process.exit(1);
  }
}

// Run the agent
main().catch(error => {
  console.error(`[${AGENT_NAME}] Fatal error:`, error);
  process.exit(1);
});
