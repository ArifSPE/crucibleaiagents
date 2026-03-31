import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { ChatMemoryPage } from "./ChatMemoryPage";
import { usePolling } from "../hooks/usePolling";

const mockPruneChatMemory = vi.fn();
const mockRegenerateChatSummary = vi.fn();
const usePollingMock = vi.mocked(usePolling);

const refreshMemory = vi.fn().mockResolvedValue(undefined);
const refreshSummary = vi.fn().mockResolvedValue(undefined);

vi.mock("../services/platformApi", () => ({
  platformApi: {
    listProviders: vi.fn(),
    pruneChatMemory: (...args: unknown[]) => mockPruneChatMemory(...args),
    regenerateChatSummary: (...args: unknown[]) => mockRegenerateChatSummary(...args),
    getChatMemory: vi.fn(),
    getChatMemorySummary: vi.fn(),
  },
}));

vi.mock("../hooks/usePolling", () => ({
  usePolling: vi.fn(),
}));

const PROVIDER = { id: 1, provider: "local_ollama", description: null, endpoint: "http://localhost:11434" };

const PROVIDERS_STATE = { data: [PROVIDER], error: null, loading: false, refresh: vi.fn() };

const MEMORY_STATE = {
  data: {
    provider_id: 1,
    provider: "local_ollama",
    conversation_id: "conv-test",
    session_id: "web-console",
    memory_count: 2,
    limit: 200,
    max_stored_turns: 20,
    memory: [
      {
        id: 1,
        llm_provider_id: 1,
        conversation_id: "conv-test",
        session_id: "web-console",
        request_id: null,
        role: "user",
        content: "hello world",
        created_at: null,
      },
      {
        id: 2,
        llm_provider_id: 1,
        conversation_id: "conv-test",
        session_id: "web-console",
        request_id: null,
        role: "assistant",
        content: "hi there",
        created_at: null,
      },
    ],
  },
  error: null,
  loading: false,
  refresh: refreshMemory,
};

const SUMMARY_STATE = {
  data: {
    provider_id: 1,
    provider: "local_ollama",
    conversation_id: "conv-test",
    session_id: "web-console",
    summary: {
      id: 10,
      llm_provider_id: 1,
      conversation_id: "conv-test",
      session_id: "web-console",
      summary_text: "User tested memory.",
      source: "llm",
      memory_count: 2,
      created_at: null,
      updated_at: null,
    },
  },
  error: null,
  loading: false,
  refresh: refreshSummary,
};

function setupPollingMock() {
  let callIndex = 0;
  usePollingMock.mockImplementation(() => {
    const states = [PROVIDERS_STATE, MEMORY_STATE, SUMMARY_STATE];
    const state = states[callIndex % 3];
    callIndex++;
    return state;
  });
}

function renderPage() {
  return render(
    <MemoryRouter>
      <ChatMemoryPage />
    </MemoryRouter>,
  );
}

describe("ChatMemoryPage", () => {
  beforeEach(() => {
    mockPruneChatMemory.mockReset();
    mockRegenerateChatSummary.mockReset();
    refreshMemory.mockClear();
    refreshSummary.mockClear();
    setupPollingMock();
  });

  afterEach(() => cleanup());

  it("renders the memory transcript and summary", () => {
    renderPage();
    expect(screen.getByText("hello world")).toBeInTheDocument();
    expect(screen.getByText("hi there")).toBeInTheDocument();
    expect(screen.getByText("User tested memory.")).toBeInTheDocument();
  });

  it("calls pruneChatMemory and shows success message", async () => {
    mockPruneChatMemory.mockResolvedValue({
      older_than_hours: 168,
      llm_provider_id: 1,
      removed_memory_count: 4,
      removed_summary_count: 1,
    });

    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "Prune expired" }));

    await waitFor(() =>
      expect(mockPruneChatMemory).toHaveBeenCalledWith({ providerId: 1, olderThanHours: 168 }),
    );
    await waitFor(() =>
      expect(screen.getByText(/Removed 4 messages/)).toBeInTheDocument(),
    );
  });

  it("regenerates the summary and calls refresh", async () => {
    mockRegenerateChatSummary.mockResolvedValue({
      provider_id: 1,
      provider: "local_ollama",
      conversation_id: "conv-test",
      session_id: "web-console",
      summary: {
        id: 11,
        summary_text: "Regenerated.",
        source: "llm",
        memory_count: 2,
        created_at: null,
        updated_at: null,
      },
    });

    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "Regenerate" }));

    await waitFor(() => expect(mockRegenerateChatSummary).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(refreshSummary).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.getByText("Summary regenerated from current conversation history.")).toBeInTheDocument(),
    );
  });
});
