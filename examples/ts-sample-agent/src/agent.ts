import { execSync } from 'child_process';

interface AgentConfig {
  name: string;
  version: string;
}

const config: AgentConfig = {
  name: 'hello-typescript',
  version: '1.0.0'
};

/**
 * Greet function - demonstrates a step in the agent workflow
 */
function greet(): void {
  console.log(`[${config.name}] Hello from TypeScript agent!`);
  console.log(`[${config.name}] Version: ${config.version}`);
  
  // Demonstrate subprocess execution
  try {
    const result = execSync('echo "subprocess says hi from TypeScript"', { encoding: 'utf-8' });
    console.log(`[${config.name}] Subprocess output: ${result.trim()}`);
  } catch (error) {
    console.error(`[${config.name}] Error running subprocess:`, error);
  }
}

/**
 * Main agent entry point
 */
async function main(): Promise<void> {
  console.log(`[${config.name}] Starting agent...`);
  
  greet();
  
  // Demonstrate async/await
  await new Promise(resolve => setTimeout(resolve, 100));
  
  console.log(`[${config.name}] Agent completed successfully`);
}

// Run the agent
main().catch(error => {
  console.error(`[${config.name}] Fatal error:`, error);
  process.exit(1);
});
