# TypeScript Sample Agent

A simple TypeScript agent demonstrating the AgentFlow platform's TypeScript support.

## Features

- ✅ TypeScript with type safety
- ✅ Async/await patterns
- ✅ Subprocess execution
- ✅ Structured logging
- ✅ Error handling

## Structure

```
ts-sample-agent/
├── manifest.json       # Agent metadata and configuration
├── package.json        # Node.js dependencies
├── src/
│   └── agent.ts       # Main agent entrypoint
└── README.md          # This file
```

## Usage

### Deploy to AgentFlow

1. **Create a ZIP package:**
   ```bash
   cd ts-sample-agent
   zip -r ../ts-sample-agent.zip manifest.json package.json src/
   ```

2. **Register and stage the package:**
   ```bash
   curl -X POST http://localhost:8080/packages/register \
     -H "Content-Type: application/json" \
     -d '{
       "name": "ts-sample-agent",
       "version": "1.0.0",
       "language": "typescript",
       "entrypoint": "src/agent.ts",
       "filename": "ts-sample-agent.zip",
       "deployment": "container"
     }'

   cp ts-sample-agent.zip "${PACKAGE_WATCHER_BASE_DIR}/incoming/"
   ```

3. **Create a run:**
   ```bash
   curl -X POST http://localhost:8080/runs \
     -H "Content-Type: application/json" \
     -d '{"package_id": YOUR_PACKAGE_ID, "inputs": {}}'
   ```

### Local Development

To test locally without the platform:

```bash
npm install
npm start
```

Or using tsx directly:
```bash
npx tsx src/agent.ts
```

## Manifest Configuration

The `manifest.json` declares this as a TypeScript agent:

```json
{
  "language": "typescript",
  "entrypoint": "src/agent.ts"
}
```

## Dependencies

Dependencies listed in `package.json` will be automatically installed by the runner using `npm install` before execution.

## Extending

Modify `src/agent.ts` to implement your custom logic:

- Add external npm packages to `package.json`
- Import additional modules
- Implement complex async workflows
- Integrate with APIs and services

## Notes

- The runner uses `tsx` for on-the-fly TypeScript execution (no compilation step needed)
- TypeScript type checking happens at runtime
- All Node.js built-in modules are available
- Environment variables can be accessed via `process.env`
