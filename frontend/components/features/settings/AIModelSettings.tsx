"use client";

import { Cpu, Database, Loader2, RefreshCw, Save } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui";
import { getUserAISettings, updateUserAISettings } from "@/lib/api/settings";
import type { UserAISettings } from "@/types";


function formatModelSize(bytes: number): string {
  if (bytes <= 0) return "Size unavailable";
  const gigabytes = bytes / 1024 ** 3;
  if (gigabytes >= 1) return `${gigabytes.toFixed(1)} GB`;
  return `${Math.round(bytes / 1024 ** 2)} MB`;
}


export function AIModelSettings() {
  const [settings, setSettings] = useState<UserAISettings | null>(null);
  const [selectedModel, setSelectedModel] = useState("");
  const [diagnosticsEnabled, setDiagnosticsEnabled] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);

  const loadSettings = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await getUserAISettings();
      setSettings(response);
      setSelectedModel(response.llm_model);
      setDiagnosticsEnabled(response.rag_diagnostics_enabled);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load AI settings.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    const initialLoadId = window.setTimeout(() => void loadSettings(), 0);
    return () => window.clearTimeout(initialLoadId);
  }, [loadSettings]);

  const selectedOption = useMemo(
    () => settings?.available_models.find((model) => model.name === selectedModel),
    [selectedModel, settings]
  );

  const hasChanges = Boolean(settings && selectedModel && (
    selectedModel !== settings.llm_model ||
    diagnosticsEnabled !== settings.rag_diagnostics_enabled
  ));

  const savePreference = async () => {
    if (!selectedModel || !hasChanges) return;
    setIsSaving(true);
    setError(null);
    setSavedMessage(null);
    try {
      const response = await updateUserAISettings({
        llm_model: selectedModel,
        rag_diagnostics_enabled: diagnosticsEnabled,
      });
      setSettings(response);
      setSelectedModel(response.llm_model);
      setSavedMessage(`Using ${response.llm_model} for new chat responses.`);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Failed to save model preference.");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Card className="border-border bg-card">
      <CardHeader className="border-b border-border">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle>Local AI model</CardTitle>
          <Badge variant={settings?.ollama_available ? "outline" : "destructive"}>
            {settings?.ollama_available ? "Ollama ready" : "Ollama offline"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 py-5">
        {isLoading ? (
          <div className="flex h-24 items-center justify-center text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
          </div>
        ) : (
          <>
            <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(240px,0.55fr)]">
              <div className="space-y-2">
                <label htmlFor="chat-model" className="text-xs font-medium text-muted-foreground">
                  Chat model
                </label>
                <Select
                  value={selectedModel}
                  onValueChange={(value) => {
                    setSelectedModel(value);
                    setSavedMessage(null);
                  }}
                  disabled={!settings?.ollama_available || settings.available_models.length === 0}
                >
                  <SelectTrigger id="chat-model" className="w-full rounded-sm border-border bg-muted">
                    <SelectValue placeholder="Select an installed model" />
                  </SelectTrigger>
                  <SelectContent className="rounded-sm">
                    {settings?.available_models.map((model) => (
                      <SelectItem key={model.name} value={model.name} className="rounded-sm">
                        {model.name} · {formatModelSize(model.size)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Cpu className="h-3.5 w-3.5" />
                  <span>{selectedOption ? formatModelSize(selectedOption.size) : "Model not installed"}</span>
                </div>
              </div>

              <div className="space-y-2">
                <p className="text-xs font-medium text-muted-foreground">Embedding model</p>
                <div className="flex h-9 items-center gap-2 border border-border bg-muted px-3 text-sm text-foreground">
                  <Database className="h-4 w-4 text-muted-foreground" />
                  <span className="truncate">{settings?.embedding_model ?? "nomic-embed-text"}</span>
                </div>
                <p className="text-xs text-muted-foreground">Used for document and note retrieval.</p>
              </div>
            </div>

            <div className="flex items-center justify-between gap-4 border-t border-border pt-4">
              <div>
                <p className="text-sm font-medium text-foreground">Retrieval diagnostics</p>
                <p className="text-xs text-muted-foreground">Show developer details for grounded chat responses.</p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={diagnosticsEnabled}
                onClick={() => {
                  setDiagnosticsEnabled((value) => !value);
                  setSavedMessage(null);
                }}
                className={`relative h-6 w-11 rounded-full border transition-colors ${diagnosticsEnabled ? "border-primary bg-primary" : "border-border bg-muted"}`}
              >
                <span className={`absolute top-0.5 h-[18px] w-[18px] rounded-full bg-background transition-[left] ${diagnosticsEnabled ? "left-[21px]" : "left-0.5"}`} />
                <span className="sr-only">Toggle retrieval diagnostics</span>
              </button>
            </div>

            {error ? <p className="border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{error}</p> : null}
            {savedMessage ? <p className="border border-border bg-muted p-3 text-sm text-foreground">{savedMessage}</p> : null}

            <div className="flex flex-wrap justify-end gap-2 border-t border-border pt-4">
              <Button type="button" variant="outline" onClick={() => void loadSettings()} disabled={isLoading || isSaving}>
                <RefreshCw className="h-4 w-4" />
                Refresh
              </Button>
              <Button type="button" onClick={() => void savePreference()} disabled={!hasChanges || isSaving}>
                {isSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                Save model
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
