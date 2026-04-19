import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { ChatPage } from "./ChatPage";
import { usePolling } from "../hooks/usePolling";

const mockSendChatMessage = vi.fn();
const mockGetProviderModels = vi.fn();
const usePollingMock = vi.mocked(usePolling);
const CHAT_DRAFTS_STORAGE_KEY = "chat.draftsByScope.v1";

const PROVIDER = { id: 1, provider: "local_ollama", description: "Local model", endpoint: "http://localhost:11434" };
const PROVIDER_2 = { id: 2, provider: "anthropic", description: "Claude", endpoint: "https://api.anthropic.com" };

vi.mock("../services/platformApi", () => ({
  platformApi: {
    sendChatMessage: (...args: unknown[]) => mockSendChatMessage(...args),
    getProviderModels: (...args: unknown[]) => mockGetProviderModels(...args),
    listProviders: vi.fn(),
  },
}));

vi.mock("../hooks/usePolling", () => ({
  usePolling: vi.fn(),
}));

function renderChat() {
  return render(
    <MemoryRouter>
      <ChatPage />
    </MemoryRouter>,
  );
}

describe("ChatPage", () => {
  let randomUuidSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    mockSendChatMessage.mockReset();
    mockGetProviderModels.mockReset();
    mockGetProviderModels.mockResolvedValue({ models: [] });
    window.localStorage.clear();
    let uuidCounter = 1;
    randomUuidSpy = vi.spyOn(globalThis.crypto, "randomUUID").mockImplementation(
      () => `00000000-0000-4000-8000-${String(uuidCounter++).padStart(12, "0")}` as `${string}-${string}-${string}-${string}-${string}`,
    );
    usePollingMock.mockReturnValue({
      data: [PROVIDER],
      error: null,
      loading: false,
      refresh: vi.fn().mockResolvedValue(undefined),
    });
  });

  afterEach(() => {
    randomUuidSpy.mockRestore();
    cleanup();
  });

  it("renders the provider in the toolbar select", () => {
    renderChat();
    expect(screen.getByRole("combobox", { name: "LLM provider" })).toBeInTheDocument();
    expect(screen.getByText("local_ollama")).toBeInTheDocument();
  });

  it("shows empty state before any messages are sent", () => {
    renderChat();
    expect(screen.getByText(/Chat with local_ollama/i)).toBeInTheDocument();
  });

  it("shows no-providers hint when provider list is empty", () => {
    usePollingMock.mockReturnValue({ data: [], error: null, loading: false, refresh: vi.fn() });
    renderChat();
    expect(screen.getByText(/No providers/i)).toBeInTheDocument();
  });

  it("sends a message and shows user text and assistant reply in the thread", async () => {
    mockSendChatMessage.mockResolvedValue({
      response: { provider_id: 1, provider: "local_ollama", model: "llama3.1", reply: "Hello there!" },
    });

    renderChat();
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "Hi!" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(screen.getByText("Hi!")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Hello there!")).toBeInTheDocument());

    expect(mockSendChatMessage).toHaveBeenCalledTimes(1);
    expect(mockSendChatMessage.mock.calls[0][0]).toBe(1);
    expect(mockSendChatMessage.mock.calls[0][1]).toMatchObject({
      provider_name: "local_ollama",
      messages: [{ role: "user", content: "Hi!" }],
      metadata: { enable_mcp_tools: false },
    });
  });

  it("sends MCP enable flag when MCP tools toggle is enabled", async () => {
    mockSendChatMessage.mockResolvedValue({
      response: {
        provider_id: 1,
        provider: "local_ollama",
        model: "llama3.1",
        reply: "Tool-backed response",
        mcp_tools: {
          enabled: true,
          planned_tools: [{ name: "ping", arguments: { message: "hello" } }],
          executed_tools: [{ name: "ping", is_error: false }],
          used_tool_count: 1,
        },
      },
    });

    renderChat();
    fireEvent.click(screen.getByRole("button", { name: "Settings" }));
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "Use tools" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(screen.getByText("Tool-backed response")).toBeInTheDocument());
    expect(screen.getByText(/MCP tools:/i)).toBeInTheDocument();
    fireEvent.click(screen.getByText("View MCP execution details"));
    expect(screen.getByText("ping")).toBeInTheDocument();
    expect(screen.getByText("ok")).toBeInTheDocument();
    expect(mockSendChatMessage.mock.calls[0][1]).toMatchObject({
      metadata: { enable_mcp_tools: true },
    });
  });

  it("shows toolbar MCP toggle and sends enabled metadata when toggled on", async () => {
    mockSendChatMessage.mockResolvedValue({
      response: { provider_id: 1, provider: "local_ollama", model: "llama3.1", reply: "Done" },
    });

    renderChat();
    expect(screen.getByRole("button", { name: "MCP: Off" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "MCP: Off" }));
    expect(screen.getByRole("button", { name: "MCP: On" })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "Use MCP now" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(mockSendChatMessage).toHaveBeenCalledTimes(1));
    expect(mockSendChatMessage.mock.calls[0][1]).toMatchObject({
      metadata: { enable_mcp_tools: true },
    });
  });

  it("clears the thread when New chat is clicked", async () => {
    mockSendChatMessage.mockResolvedValue({
      response: { provider_id: 1, provider: "local_ollama", model: "llama3.1", reply: "Acknowledged." },
    });

    renderChat();
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "Remember this." } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(screen.getByText("Acknowledged.")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "New chat" }));
    expect(screen.queryByText("Remember this.")).not.toBeInTheDocument();
    expect(screen.queryByText("Acknowledged.")).not.toBeInTheDocument();
  });

  it("restores draft per selected provider scope", () => {
    usePollingMock.mockReturnValue({
      data: [PROVIDER, PROVIDER_2],
      error: null,
      loading: false,
      refresh: vi.fn().mockResolvedValue(undefined),
    });

    renderChat();

    const providerSelect = screen.getByRole("combobox", { name: "LLM provider" });
    const messageInput = screen.getByLabelText("Message") as HTMLTextAreaElement;

    fireEvent.change(messageInput, { target: { value: "Draft for provider one" } });
    expect(messageInput.value).toBe("Draft for provider one");

    fireEvent.change(providerSelect, { target: { value: "2" } });
    expect((screen.getByLabelText("Message") as HTMLTextAreaElement).value).toBe("");

    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "Draft for provider two" } });
    expect((screen.getByLabelText("Message") as HTMLTextAreaElement).value).toBe("Draft for provider two");

    fireEvent.change(providerSelect, { target: { value: "1" } });
    expect((screen.getByLabelText("Message") as HTMLTextAreaElement).value).toBe("Draft for provider one");
  });

  it("hydrates draft from localStorage for active scope", () => {
    window.localStorage.setItem(
      CHAT_DRAFTS_STORAGE_KEY,
      JSON.stringify({ "1:conv-00000000-0000-4000-8000-000000000001": "Restored from storage" }),
    );

    renderChat();

    expect((screen.getByLabelText("Message") as HTMLTextAreaElement).value).toBe("Restored from storage");
  });

  it("persists scoped draft changes to localStorage", () => {
    renderChat();

    const messageInput = screen.getByLabelText("Message") as HTMLTextAreaElement;
    fireEvent.change(messageInput, { target: { value: "Persist me" } });

    const saved = window.localStorage.getItem(CHAT_DRAFTS_STORAGE_KEY);
    expect(saved).not.toBeNull();
    expect(saved).toContain("Persist me");
  });
});


