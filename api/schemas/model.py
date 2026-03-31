from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone
from utils.db import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AgentPackage(Base):
    __tablename__ = 'agent_packages'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    version: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now, onupdate=_utc_now)
    description_json: Mapped[dict] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    language: Mapped[str] = mapped_column(String, nullable=True)
    storage_path: Mapped[str] = mapped_column(String, nullable=True)
    entry_point: Mapped[str] = mapped_column(String, nullable=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=60)
    filename: Mapped[str] = mapped_column(String, nullable=True)

    #LLM configuration fields
    llm_model: Mapped[str] = mapped_column(String, nullable=True)
    llm_temperature: Mapped[float] = mapped_column(Integer, default=0.7)
    llm_max_tokens: Mapped[int] = mapped_column(Integer, default=2048)

    #Schema information fields
    schedule_enables: Mapped[bool] = mapped_column(Boolean, default=False)
    schedule_type: Mapped[str] = mapped_column(String, nullable=True)  # e.g., 'cron', 'interval'
    schedule_congig: Mapped[dict] = mapped_column(JSON, nullable=True)  # e.g., {'cron': '0 0 * * *'} or {'interval': '1h'}
    disable_reason: Mapped[str] = mapped_column(String, nullable=True)
    disabled_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    disabled_by: Mapped[str] = mapped_column(String, nullable=True)    
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)

    #Deamon mode configuration fields
    runtime_mode: Mapped[str] = mapped_column(String,default='batch', nullable=True)  # e.g., 'daemon', 'batch'
    health_check_config: Mapped[dict] = mapped_column(JSON, nullable=True)  # e.g., {'interval': '30s', 'timeout': '5s'}
    restart_policy: Mapped[str] = mapped_column(String, default='on-failure', nullable=True)  # e.g., 'always', 'on-failure', 'never'
    deamon_auto_restart: Mapped[bool] = mapped_column(Boolean, default=False)
    demaon_endpoint_config: Mapped[dict] = mapped_column(JSON, nullable=True)  # e.g., {'port': 8080, 'health_check_path': '/health'}
    expoded_port: Mapped[int] = mapped_column(Integer, nullable=True)
    deployment: Mapped[str] = mapped_column(String, default="local", nullable=True)  # local, container

class Runs(Base):
    __tablename__ = 'runs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    agent_package_id: Mapped[int] = mapped_column(Integer, ForeignKey('agent_packages.id'), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)  # e.g., 'pending', 'running', 'completed', 'failed'
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=60)
    exit_code: Mapped[int] = mapped_column(Integer, nullable=True)
    error: Mapped[str] = mapped_column(Text, nullable=True)

     # Daemon mode fields
    runtime_mode: Mapped[str] = mapped_column(String, default="batch")  # batch, daemon
    container_id: Mapped[str] = mapped_column(String, nullable=True)  # Docker container ID for daemon runs
    last_health_check: Mapped[datetime] = mapped_column(DateTime, nullable=True)  # Last successful health check
    restart_count: Mapped[int] = mapped_column(Integer, default=0)  # Number of restarts for daemon runs
    stopped_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)  # When daemon was stopped
    exposed_port: Mapped[int] = mapped_column(Integer, nullable=True)  # Host port Docker mapped for daemon HTTP endpoint

class RunEvents(Base):
    __tablename__ = "run_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("runs.id"), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)
    type: Mapped[str] = mapped_column(String, nullable=False)  # runner_boot, subprocess_start, step_start, etc.
    level: Mapped[str] = mapped_column(String, default="INFO")  # INFO, WARNING, ERROR, DEBUG
    category: Mapped[str] = mapped_column(String, default="system")  # system, agent, infrastructure, telemetry
    source: Mapped[str] = mapped_column(String, nullable=True)  # runner, worker, agent, subprocess
    message: Mapped[str] = mapped_column(Text, nullable=True)  # Human-readable summary
    payload_jason: Mapped[str] = mapped_column(Text, nullable=False)  # Full JSON payload for details

class RunLogs(Base):
    __tablename__ = "run_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("runs.id"), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)
    stream: Mapped[str] = mapped_column(String, nullable=False)  # stdout, stderr
    level: Mapped[str] = mapped_column(String, default="INFO")  # INFO, WARNING, ERROR, DEBUG
    line: Mapped[str] = mapped_column(Text, nullable=False)
    section: Mapped[str] = mapped_column(String, nullable=True)  # Optional: agent, dependency, system, etc.

class PackageSchedule(Base):
    __tablename__ = "package_schedules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    package_id: Mapped[int] = mapped_column(Integer, ForeignKey("agent_packages.id"), nullable=False)
    schedule_type: Mapped[str] = mapped_column(String, nullable=False)  # interval, cron, at
    schedule_config: Mapped[str] = mapped_column(Text, nullable=False)  # JSON: {interval_seconds, cron_expr, etc}
    is_active: Mapped[bool] = mapped_column(default=True)
    last_run_time: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    next_run_time: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)

class PackageSecret(Base):
    __tablename__ = "package_secrets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    package_id: Mapped[int] = mapped_column(Integer, ForeignKey("agent_packages.id"), nullable=False)
    key_name: Mapped[str] = mapped_column(String, nullable=False)  # e.g., "MS_TEAMS_CLIENT_SECRET"
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)  # Encrypted secret value
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now, onupdate=_utc_now)


class LlmProvider(Base):
    __tablename__ = "llm_providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider: Mapped[str] = mapped_column(String, nullable=False)  # local_ollama, ollama_cloud, ibm_watson, aws_bedrock, anthropic, claude
    description: Mapped[str] = mapped_column(Text, nullable=True)
    endpoint: Mapped[str] = mapped_column(String, nullable=True)
    encrypted_credentials: Mapped[str] = mapped_column(Text, nullable=True)  # Encrypted JSON object of credential key-values
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now, onupdate=_utc_now)

    credential: Mapped[list["LLMCredential"]] = relationship(
        "LLMCredential",
        back_populates="provider",
        cascade="all, delete-orphan",
        lazy="selectin")


class LLMCredential(Base):
    __tablename__ = "llm_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    llm_provider_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("llm_providers.id"),
        nullable=False,
    )
    key_name: Mapped[str] = mapped_column(String, nullable=False)  
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)  # Encrypted credential value
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now, onupdate=_utc_now)

    provider: Mapped["LlmProvider"] = relationship(
        "LlmProvider",
        back_populates="credential")


class LLMChatMemory(Base):
    __tablename__ = "llm_chat_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    llm_provider_id: Mapped[int] = mapped_column(Integer, ForeignKey("llm_providers.id"), nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(String, nullable=True, index=True)
    session_id: Mapped[str] = mapped_column(String, nullable=True, index=True)
    request_id: Mapped[str] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String, nullable=False)  # user, assistant, system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now, index=True)


class LLMChatSummary(Base):
    __tablename__ = "llm_chat_summary"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    llm_provider_id: Mapped[int] = mapped_column(Integer, ForeignKey("llm_providers.id"), nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(String, nullable=True, index=True)
    session_id: Mapped[str] = mapped_column(String, nullable=True, index=True)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False, default="llm")  # llm or fallback
    memory_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now, onupdate=_utc_now, index=True)