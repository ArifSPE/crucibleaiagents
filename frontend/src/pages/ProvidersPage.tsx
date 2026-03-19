import { useState } from "react";
import { EmptyState } from "../components/EmptyState";
import { SectionCard } from "../components/SectionCard";
import { usePolling } from "../hooks/usePolling";
import { platformApi } from "../services/platformApi";
import type { LlmProviderUpsertRequest } from "../types/api";

const defaultProviderForm: LlmProviderUpsertRequest = {
  provider_name: "",
  description: "",
  endpoint: "",
  credentials: {},
};

export function ProvidersPage() {
  const providersState = usePolling(() => platformApi.listProviders(), 15000);
  const [providerForm, setProviderForm] = useState<LlmProviderUpsertRequest>(defaultProviderForm);
  const [credentialsText, setCredentialsText] = useState('{\n  "api_key": ""\n}');
  const [feedback, setFeedback] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setFeedback(null);
    try {
      const credentials = credentialsText.trim() ? JSON.parse(credentialsText) as Record<string, string> : undefined;
      await platformApi.createProvider({
        ...providerForm,
        credentials,
      });
      await providersState.refresh();
      setProviderForm(defaultProviderForm);
      setCredentialsText('{\n  "api_key": ""\n}');
      setFeedback("Provider created successfully.");
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "Failed to create provider.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page-grid page-grid--two-column">
      <SectionCard title="Configured providers" subtitle="Managed model backends and endpoints">
        {providersState.loading ? <div className="page-state">Loading providers...</div> : null}
        {providersState.error ? <div className="page-state page-state--error">{providersState.error}</div> : null}
        {providersState.data?.length ? (
          <ul className="provider-list">
            {providersState.data.map((provider) => (
              <li key={provider.id}>
                <div>
                  <strong>{provider.provider}</strong>
                  <p>{provider.description || "No description"}</p>
                </div>
                <span>{provider.endpoint || "No endpoint"}</span>
              </li>
            ))}
          </ul>
        ) : !providersState.loading ? (
          <EmptyState title="No LLM providers" description="Register a provider to support agents that depend on managed model backends." />
        ) : null}
      </SectionCard>

      <SectionCard title="Add provider" subtitle="Credentials are encrypted server-side before storage">
        <form className="form-grid" onSubmit={handleSubmit}>
          <label>
            <span>Provider name</span>
            <input value={providerForm.provider_name} onChange={(event) => setProviderForm((prev) => ({ ...prev, provider_name: event.target.value }))} required />
          </label>
          <label>
            <span>Endpoint</span>
            <input value={providerForm.endpoint || ""} onChange={(event) => setProviderForm((prev) => ({ ...prev, endpoint: event.target.value }))} />
          </label>
          <label className="form-grid__wide">
            <span>Description</span>
            <textarea value={providerForm.description || ""} onChange={(event) => setProviderForm((prev) => ({ ...prev, description: event.target.value }))} rows={3} />
          </label>
          <label className="form-grid__wide">
            <span>Credentials JSON</span>
            <textarea rows={8} value={credentialsText} onChange={(event) => setCredentialsText(event.target.value)} />
          </label>
          <div className="form-actions form-grid__wide">
            <button className="button button--primary" disabled={saving} type="submit">
              {saving ? "Saving..." : "Create provider"}
            </button>
          </div>
        </form>
        {feedback ? <p className="inline-feedback">{feedback}</p> : null}
      </SectionCard>
    </div>
  );
}