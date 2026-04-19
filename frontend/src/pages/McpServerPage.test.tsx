import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { McpServerPage } from "./McpServerPage";
import { usePolling } from "../hooks/usePolling";

vi.mock("../hooks/usePolling", () => ({
  usePolling: vi.fn(),
}));

const usePollingMock = vi.mocked(usePolling);

describe("McpServerPage", () => {
  beforeEach(() => {
    usePollingMock.mockReset();
  });

  it("renders tools, resources, and prompts from the new MCP features", () => {
    usePollingMock
      .mockReturnValueOnce({
        data: { status: "ok", server_url: "http://mcp_server:9001/mcp", tool_count: 8, resource_count: 1, prompt_count: 2 },
        loading: false,
        error: null,
        refresh: vi.fn(),
      })
      .mockReturnValueOnce({
        data: { server_url: "http://mcp_server:9001/mcp", tools: [{ name: "read_workspace_file", description: "Read workspace files", input_schema: { type: "object" } }] },
        loading: false,
        error: null,
        refresh: vi.fn(),
      })
      .mockReturnValueOnce({
        data: { server_url: "http://mcp_server:9001/mcp", resources: [{ uri: "file://workspace/README.md", name: "README", description: "Workspace README", mime_type: "text/markdown" }] },
        loading: false,
        error: null,
        refresh: vi.fn(),
      })
      .mockReturnValueOnce({
        data: { server_url: "http://mcp_server:9001/mcp", prompts: [{ name: "summarize_workspace_file", description: "Summarize a file", arguments: [{ name: "filepath", required: true }] }] },
        loading: false,
        error: null,
        refresh: vi.fn(),
      });

    render(<McpServerPage />);

    expect(screen.getByRole("heading", { name: /registered tools/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /registered resources/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /prompt templates/i })).toBeInTheDocument();
    expect(screen.getByText("read_workspace_file")).toBeInTheDocument();
    expect(screen.getByText("file://workspace/README.md")).toBeInTheDocument();
    expect(screen.getByText("summarize_workspace_file")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /render prompt/i })).toBeInTheDocument();
  });
});
