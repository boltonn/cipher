"use client";

import { GradientButton } from "@/components/ui/gradient-button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  ANALYTICS,
  datasetRequestSchema,
  paramSchemas,
  type AnalyticDef,
  type DatasetRequestResult,
  type EnrichmentType,
} from "@/features/datasets/request-types";
import {
  useDatasetRequestConfig,
  useRequestDataset,
} from "@/features/datasets/hooks/use-request-dataset";
import { cn } from "@/lib/utils";
import { ArrowUpRight, CheckCircle2, Sparkles } from "lucide-react";
import { useState } from "react";

interface DatasetRequestFormProps {
  /** Called when the user dismisses the form (cancel, or done after success). */
  onClose?: () => void;
}

type ParamValues = Record<string, string>;

interface FormState {
  datasetId: string;
  name: string;
  reason: string;
  analytics: Record<string, { enabled: boolean; params: ParamValues }>;
}

function buildInitialState(): FormState {
  return {
    datasetId: "",
    name: "",
    reason: "",
    analytics: Object.fromEntries(
      ANALYTICS.map((analytic) => [
        analytic.type,
        {
          enabled: false,
          params: Object.fromEntries(
            analytic.params.map((param) => [param.key, String(param.defaultValue ?? "")])
          ),
        },
      ])
    ),
  };
}

export function DatasetRequestForm({ onClose }: DatasetRequestFormProps) {
  const [form, setForm] = useState<FormState>(buildInitialState);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DatasetRequestResult | null>(null);

  const { data: config } = useDatasetRequestConfig();
  const { mutate, isPending } = useRequestDataset(setResult);

  const setParam = (type: EnrichmentType, key: string, value: string) =>
    setForm((prev) => ({
      ...prev,
      analytics: {
        ...prev.analytics,
        [type]: {
          ...prev.analytics[type],
          params: { ...prev.analytics[type].params, [key]: value },
        },
      },
    }));

  const toggleAnalytic = (type: EnrichmentType, enabled: boolean) =>
    setForm((prev) => ({
      ...prev,
      analytics: {
        ...prev.analytics,
        [type]: { ...prev.analytics[type], enabled },
      },
    }));

  const handleSubmit = () => {
    setError(null);

    const analytics: {
      enrichmentType: EnrichmentType;
      parameters: Record<string, unknown>;
    }[] = [];

    for (const def of ANALYTICS) {
      const selection = form.analytics[def.type];
      if (!selection.enabled) continue;

      const raw: Record<string, unknown> = {};
      for (const param of def.params) {
        const value = (selection.params[param.key] ?? "").trim();
        if (value === "") {
          if (param.optional) continue;
          setError(`${def.label}: ${param.label} is required`);
          return;
        }
        raw[param.key] = param.kind === "number" ? Number(value) : value;
      }

      const parsed = paramSchemas[def.type].safeParse(raw);
      if (!parsed.success) {
        setError(`${def.label}: ${parsed.error.issues[0].message}`);
        return;
      }
      analytics.push({
        enrichmentType: def.type,
        parameters: parsed.data as Record<string, unknown>,
      });
    }

    const validated = datasetRequestSchema.safeParse({
      datasetId: form.datasetId,
      name: form.name || undefined,
      reason: form.reason,
      analytics,
    });
    if (!validated.success) {
      setError(validated.error.issues[0].message);
      return;
    }
    mutate(validated.data);
  };

  return (
    <div className="shadow-input mx-auto w-full max-w-lg rounded-none bg-card md:rounded-2xl">
      <div className="max-h-[80vh] overflow-y-auto p-4 md:p-8">
        <h2 className="text-xl font-bold text-foreground">Request a Dataset</h2>
        <p className="mt-2 max-w-sm text-sm text-muted-foreground">
          File a request to ingest and process a dataset. This opens a GitHub issue
          {config?.repo ? ` in ${config.repo}` : ""}.
        </p>

        {config?.issuesUrl && (
          <a
            href={config.issuesUrl}
            target="_blank"
            rel="noreferrer"
            className="mt-3 inline-flex items-center gap-1 text-xs text-primary hover:underline"
          >
            View existing requests to thumbs-up
            <ArrowUpRight size={12} />
          </a>
        )}

        {result ? (
          <div className="my-8 space-y-4">
            <div className="flex items-start gap-3 rounded-lg border border-primary/20 bg-primary/5 px-4 py-3">
              <CheckCircle2 size={18} className="mt-0.5 shrink-0 text-primary" />
              <div className="text-sm">
                <p className="font-medium text-foreground">
                  Request filed as issue #{result.issueNumber}
                </p>
                <a
                  href={result.issueUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-1 inline-flex items-center gap-1 text-xs text-primary hover:underline"
                >
                  Open the issue
                  <ArrowUpRight size={12} />
                </a>
              </div>
            </div>
            <GradientButton type="button" onClick={onClose}>
              Done
            </GradientButton>
          </div>
        ) : (
          <form
            className="my-8"
            onSubmit={(event) => {
              event.preventDefault();
              handleSubmit();
            }}
          >
            <div className="mb-4 flex flex-col space-y-2">
              <Label htmlFor="dr-dataset-id">Dataset ID</Label>
              <Input
                id="dr-dataset-id"
                value={form.datasetId}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, datasetId: event.target.value }))
                }
                placeholder="e.g. 2026-q2-comms-dump"
              />
            </div>

            <div className="mb-4 flex flex-col space-y-2">
              <Label htmlFor="dr-name">
                Name <span className="text-muted-foreground">(optional)</span>
              </Label>
              <Input
                id="dr-name"
                value={form.name}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, name: event.target.value }))
                }
                placeholder="Q2 Communications Dump"
              />
            </div>

            <div className="mb-6 flex flex-col space-y-2">
              <Label htmlFor="dr-reason">Reason for request</Label>
              <Textarea
                id="dr-reason"
                value={form.reason}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, reason: event.target.value }))
                }
                placeholder="What is this dataset, where does it come from, and why is it needed?"
                rows={4}
              />
            </div>

            <div className="mb-6">
              <div className="mb-3 flex items-center gap-2">
                <Sparkles size={14} className="text-annotation" />
                <span className="text-sm font-medium text-foreground">Analytics to run</span>
              </div>
              <div className="space-y-2">
                {ANALYTICS.map((analytic) => (
                  <AnalyticRow
                    key={analytic.type}
                    analytic={analytic}
                    enabled={form.analytics[analytic.type].enabled}
                    values={form.analytics[analytic.type].params}
                    onToggle={(enabled) => toggleAnalytic(analytic.type, enabled)}
                    onParamChange={(key, value) => setParam(analytic.type, key, value)}
                  />
                ))}
              </div>
            </div>

            {error && (
              <p className="mb-4 rounded-lg border border-destructive/20 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                {error}
              </p>
            )}

            <div className="flex gap-3">
              {onClose && (
                <button
                  type="button"
                  onClick={onClose}
                  className="h-10 flex-1 rounded-md border border-border text-sm text-muted-foreground hover:text-foreground"
                >
                  Cancel
                </button>
              )}
              <GradientButton type="submit" isLoading={isPending} loadingText="Filing…">
                Submit Request →
              </GradientButton>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

interface AnalyticRowProps {
  analytic: AnalyticDef;
  enabled: boolean;
  values: ParamValues;
  onToggle: (enabled: boolean) => void;
  onParamChange: (key: string, value: string) => void;
}

function AnalyticRow({ analytic, enabled, values, onToggle, onParamChange }: AnalyticRowProps) {
  return (
    <div
      className={cn(
        "rounded-lg border px-3 py-2.5 transition-colors",
        enabled ? "border-annotation/40 bg-annotation/5" : "border-border bg-muted/30"
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm text-foreground">{analytic.label}</p>
          <p className="text-xs text-muted-foreground">{analytic.description}</p>
        </div>
        <Switch checked={enabled} onCheckedChange={onToggle} aria-label={analytic.label} />
      </div>

      {enabled && analytic.params.length > 0 && (
        <div className="mt-3 grid grid-cols-2 gap-3 border-t border-border/60 pt-3">
          {analytic.params.map((param) => (
            <div key={param.key} className="flex flex-col space-y-1">
              <Label htmlFor={`${analytic.type}-${param.key}`} className="text-xs text-muted-foreground">
                {param.label}
                {param.optional && " (optional)"}
              </Label>
              {param.kind === "select" ? (
                <Select
                  value={values[param.key] || String(param.defaultValue)}
                  onValueChange={(value) => onParamChange(param.key, value)}
                >
                  <SelectTrigger id={`${analytic.type}-${param.key}`} className="h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {param.options?.map((option) => (
                      <SelectItem key={option} value={option} className="text-xs">
                        {option}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <Input
                  id={`${analytic.type}-${param.key}`}
                  type={param.kind === "number" ? "number" : "text"}
                  value={values[param.key] ?? ""}
                  min={param.min}
                  max={param.max}
                  step={param.step}
                  placeholder={param.optional ? "default" : undefined}
                  onChange={(event) => onParamChange(param.key, event.target.value)}
                  className="h-8 text-xs"
                />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
