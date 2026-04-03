export interface HealthResponse {
  status: string;
  service: string;
  timestamp: string;
}

export interface AgentPackage {
  id: number;
  created_at: string | null;
  filename: string | null;
  name: string;
  version: string;
  description: string | null;
  language: string | null;
  entrypoint: string | null;
  timeout_seconds: number | null;
  schedule_enabled: boolean | null;
  schedule_type: string | null;
  schedule_config: Record<string, unknown> | string | null;
  secret_keys: string[];
  schedule_requested_enabled: boolean | null;
  schedule_activation_blocked: boolean;
  missing_secret_keys: string[];
  disabled: boolean;
  runtime_mode: string | null;
  deployment: string;
  restart_policy: string | null;
  daemon_auto_start: boolean | null;
  exposed_port: number | null;
}

export interface RunSummary {
  id: number;
  agent_package_id: number;
  status: string;
  runtime_mode: string | null;
  started_at: string | null;
  completed_at: string | null;
  stopped_at: string | null;
  timeout_seconds: number | null;
  exit_code: number | null;
  error: string | null;
  container_id: string | null;
  last_health_check: string | null;
  restart_count: number | null;
  exposed_port: number | null;
}

export interface RunLog {
  id: number;
  run_id: number;
  ts: string | null;
  stream: string;
  level: string;
  line: string;
  section: string | null;
}

export interface RunEvent {
  id: number;
  run_id: number;
  ts: string | null;
  type: string;
  level: string | null;
  category: string | null;
  source: string | null;
  message: string | null;
  payload_jason: string | null;
}

export interface PackageSchedule {
  id: number;
  package_id: number;
  schedule_type: string;
  schedule_config: string | null;
  is_active: boolean;
  last_run_time: string | null;
  next_run_time: string | null;
  created_at: string | null;
}

export interface PackageSecret {
  id: number;
  package_id: number;
  key_name: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface LlmProvider {
  id: number;
  provider: string;
  description: string | null;
  endpoint: string | null;
  has_credentials: boolean;
  credential_keys: string[];
  created_at: string | null;
  updated_at: string | null;
}

export interface LlmModel {
  provider_id: number;
  provider: string;
  model_endpoint: string;
  id: string;
  display_name?: string | null;
  created_at?: string | null;
  type?: string | null;
  capabilities?: Record<string, unknown> | null;
  max_input_tokens?: number | null;
  max_tokens?: number | null;
}

export interface LlmModelsListResponse {
  models: LlmModel[];
}

export interface ChatMessagePayload {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface ChatRequest {
  provider_name: string;
  message?: string;
  model?: string;
  system_prompt?: string;
  messages?: ChatMessagePayload[];
  short_term_memory?: ChatMessagePayload[];
  memory_strategy?: "append" | "window" | "summary";
  memory_window_size?: number;
  conversation_id?: string;
  session_id?: string;
  request_id?: string;
  temperature?: number;
  top_p?: number;
  max_tokens?: number;
  metadata?: Record<string, unknown>;
}

export interface ChatProviderResponse {
  provider_id: number;
  provider: string;
  endpoint?: string;
  model?: string;
  reply: string;
}

export interface ChatResponseEnvelope {
  response: ChatProviderResponse;
}

export interface ChatMemoryItem {
  id: number;
  llm_provider_id: number;
  conversation_id: string | null;
  session_id: string | null;
  request_id: string | null;
  role: "system" | "user" | "assistant";
  content: string;
  created_at: string | null;
}

export interface ChatMemoryResponse {
  provider_id: number;
  provider: string;
  conversation_id: string | null;
  session_id: string | null;
  memory_count: number;
  limit: number;
  max_stored_turns: number;
  memory: ChatMemoryItem[];
}

export interface ChatMemorySummary {
  id: number;
  llm_provider_id: number;
  conversation_id: string | null;
  session_id: string | null;
  summary_text: string;
  source: string;
  memory_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface ChatMemorySummaryResponse {
  provider_id: number;
  provider: string;
  conversation_id: string | null;
  session_id: string | null;
  summary: ChatMemorySummary | null;
}

export interface ChatMemoryPruneResponse {
  older_than_hours: number;
  llm_provider_id: number | null;
  removed_memory_count: number;
  removed_summary_count: number;
}

export interface PackageRegisterRequest {
  name: string;
  version: string;
  description?: string;
  language?: string;
  entrypoint?: string;
  timeout_seconds?: number;
  filename?: string;
  runtime_mode?: string;
  deployment?: string;
  restart_policy?: string;
  daemon_auto_start?: boolean;
  exposed_port?: number;
  schedule_enabled?: boolean;
  schedule_type?: string;
  schedule_config?: Record<string, unknown>;
  secret_keys?: string[];
}

export interface ScheduleUpsertRequest {
  schedule_type: string;
  interval_seconds?: number;
  cron_expression?: string;
  timestamp?: string;
  timeout_seconds?: number;
  enabled?: boolean;
}

export interface SecretUpsertRequest {
  key_name: string;
  value: string;
}

export interface LlmProviderUpsertRequest {
  provider_name: string;
  description?: string;
  endpoint?: string;
  credentials?: Record<string, string>;
}

export interface CreatedEntity {
  id: number;
}