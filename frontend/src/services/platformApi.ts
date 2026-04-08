import { apiFetch } from "./apiClient";
import type {
  AgentPackage,
  ChatMemoryPruneResponse,
  ChatMemoryResponse,
  ChatMemorySummaryResponse,
  ChatRequest,
  ChatResponseEnvelope,
  CreatedEntity,
  HealthResponse,
  LlmModelsListResponse,
  LlmProvider,
  LlmProviderUpsertRequest,
  McpHealthResponse,
  McpToolsListResponse,
  PackageRegisterRequest,
  PackageSchedule,
  PackageSecret,
  RunEvent,
  RunLog,
  RunSummary,
  ScheduleUpsertRequest,
  SecretUpsertRequest,
} from "../types/api";

export const platformApi = {
  health: () => apiFetch<HealthResponse>("/health"),
  mcpHealth: () => apiFetch<McpHealthResponse>("/mcp/health"),
  listMcpTools: () => apiFetch<McpToolsListResponse>("/mcp/tools"),
  listPackages: () => apiFetch<AgentPackage[]>("/packages"),
  listPackage: (packageId: number) => apiFetch<AgentPackage>(`/packages/${packageId}`),
  getPackage: (packageId: number) => apiFetch<AgentPackage>(`/packages/${packageId}`),
  registerPackage: (payload: PackageRegisterRequest) =>
    apiFetch<CreatedEntity>("/packages/register", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  listRuns: () => apiFetch<RunSummary[]>("/runs"),
  createRun: (packageId: number) => apiFetch<RunSummary>(`/runs`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ package_id: packageId }) }),
  getRun: (runId: number) => apiFetch<RunSummary>(`/runs/${runId}`),
  getPackageRuns: (packageId: number) => apiFetch<RunSummary[]>(`/runs/package/${packageId}`),
  getRunLogs: (runId: number) => apiFetch<RunLog[]>(`/runs/${runId}/logs`),
  getRunEvents: (runId: number) => apiFetch<RunEvent[]>(`/runs/${runId}/events`),
  listSchedules: () => apiFetch<PackageSchedule[]>("/schedules"),
  listPackageSchedules: (packageId: number) => apiFetch<PackageSchedule[]>(`/packages/${packageId}/schedules`),
  createPackageSchedule: (packageId: number, payload: ScheduleUpsertRequest) =>
    apiFetch<PackageSchedule>(`/packages/${packageId}/schedules`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  listPackageSecrets: (packageId: number) => apiFetch<PackageSecret[]>(`/packages/${packageId}/secrets`),
  createPackageSecret: (packageId: number, payload: SecretUpsertRequest) =>
    apiFetch<PackageSecret>(`/packages/${packageId}/secrets`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updatePackageSecret: (packageId: number, secretId: number, payload: SecretUpsertRequest) =>
    apiFetch<PackageSecret>(`/packages/${packageId}/secrets/${secretId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  deletePackageSecret: (packageId: number, secretId: number) =>
    apiFetch<void>(`/packages/${packageId}/secrets/${secretId}`, { method: "DELETE" }),
  listProviders: () => apiFetch<LlmProvider[]>("/llm-providers"),
  getProviderModels: (providerId: number) => apiFetch<LlmModelsListResponse>(`/llm-providers/${providerId}/models`),
  createProvider: (payload: LlmProviderUpsertRequest) =>
    apiFetch<LlmProvider>("/llm-providers", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateProvider: (providerId: number, payload: LlmProviderUpsertRequest) =>
    apiFetch<LlmProvider>(`/llm-providers/${providerId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  deleteProvider: (providerId: number) =>
    apiFetch<void>(`/llm-providers/${providerId}`, { method: "DELETE" }),
  sendChatMessage: (providerId: number, payload: ChatRequest) =>
    apiFetch<ChatResponseEnvelope>(`/chat/${providerId}`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getChatMemory: (providerId: number, scope: { conversationId?: string; sessionId?: string; limit?: number }) => {
    const params = new URLSearchParams();
    if (scope.conversationId) {
      params.set("conversation_id", scope.conversationId);
    }
    if (scope.sessionId) {
      params.set("session_id", scope.sessionId);
    }
    if (typeof scope.limit === "number") {
      params.set("limit", String(scope.limit));
    }
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return apiFetch<ChatMemoryResponse>(`/chat/${providerId}/memory${suffix}`);
  },
  getChatMemorySummary: (providerId: number, scope: { conversationId?: string; sessionId?: string }) => {
    const params = new URLSearchParams();
    if (scope.conversationId) {
      params.set("conversation_id", scope.conversationId);
    }
    if (scope.sessionId) {
      params.set("session_id", scope.sessionId);
    }
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return apiFetch<ChatMemorySummaryResponse>(`/chat/${providerId}/memory/summary${suffix}`);
  },
  pruneChatMemory: (scope: { olderThanHours?: number; providerId?: number }) => {
    const params = new URLSearchParams();
    if (typeof scope.olderThanHours === "number") {
      params.set("older_than_hours", String(scope.olderThanHours));
    }
    if (typeof scope.providerId === "number") {
      params.set("llm_provider_id", String(scope.providerId));
    }
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return apiFetch<ChatMemoryPruneResponse>(`/chat/memory/prune${suffix}`, {
      method: "POST",
    });
  },
  regenerateChatSummary: (providerId: number, scope: { conversationId?: string; sessionId?: string }) => {
    const params = new URLSearchParams();
    if (scope.conversationId) {
      params.set("conversation_id", scope.conversationId);
    }
    if (scope.sessionId) {
      params.set("session_id", scope.sessionId);
    }
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return apiFetch<ChatMemorySummaryResponse>(`/chat/${providerId}/memory/summary/regenerate${suffix}`, {
      method: "POST",
    });
  },
};