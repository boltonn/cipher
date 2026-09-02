"use client";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
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
import {
  Stepper,
  StepperIndicator,
  StepperItem,
  StepperNav,
  StepperSeparator,
  StepperTitle,
  StepperTrigger,
} from "@/components/ui/stepper";
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
import { ArrowLeft, ArrowRight, ArrowUpRight, CheckCircle2, Sparkles } from "lucide-react";
import { useState } from "react";

const detailsSchema = datasetRequestSchema.pick({
  datasetId: true,
  name: true,
  reason: true,
});

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
  const [step, setStep] = useState<1 | 2>(1);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<{
    datasetId?: string[];
    name?: string[];
    reason?: string[];
  }>({});
  const [result, setResult] = useState<DatasetRequestResult | null>(null);

  const { data: config } = useDatasetRequestConfig();
  const { mutate, isPending } = useRequestDataset(setResult);

  const enabledCount = ANALYTICS.filter((a) => form.analytics[a.type].enabled).length;

  /** Validate the step-1 fields; on failure populate `fieldErrors` and stay put. */
  const validateDetails = () => {
    const parsed = detailsSchema.safeParse({
      datasetId: form.datasetId,
      name: form.name || undefined,
      reason: form.reason,
    });
    if (parsed.success) {
      setFieldErrors({});
      return true;
    }
    const fe = parsed.error.flatten().fieldErrors;
    setFieldErrors({ datasetId: fe.datasetId, name: fe.name, reason: fe.reason });
    return false;
  };

  const goToStep = (next: number) => {
    setError(null);
    if (next <= step || validateDetails()) setStep(next as 1 | 2);
  };

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
    setFieldErrors({});

    const analytics: {
      enrichmentType: EnrichmentType;
      parameters: Record<string, unknown>;
    }[] = [];

    for (const def of ANALYTICS) {
      const selection = form.analytics[def.type];
      if (!selection.enabled) continue;

      // Params are bucketed by the enrichment they belong to, so a composite
      // analytic (e.g. Face recognition) can split them across the entries it
      // emits (face_detection + face_matching).
      const rawByOwner: Record<string, Record<string, unknown>> = {};
      for (const param of def.params) {
        const owner = param.owner ?? def.type;
        const value = (selection.params[param.key] ?? "").trim();
        if (value === "") {
          if (param.optional) continue;
          setError(`${def.label}: ${param.label} is required`);
          return;
        }
        const bucket = (rawByOwner[owner] ||= {});
        bucket[param.key] = param.kind === "number" ? Number(value) : value;
      }

      for (const emitType of def.emits ?? [def.type]) {
        const parsed = paramSchemas[emitType].safeParse(rawByOwner[emitType] ?? {});
        if (!parsed.success) {
          setError(`${def.label}: ${parsed.error.issues[0].message}`);
          return;
        }
        analytics.push({
          enrichmentType: emitType,
          parameters: parsed.data as Record<string, unknown>,
        });
      }
    }

    const validated = datasetRequestSchema.safeParse({
      datasetId: form.datasetId,
      name: form.name || undefined,
      reason: form.reason,
      analytics,
    });
    if (!validated.success) {
      const fe = validated.error.flatten().fieldErrors;
      setFieldErrors({ datasetId: fe.datasetId, name: fe.name, reason: fe.reason });
      if (fe.datasetId?.length || fe.name?.length || fe.reason?.length) {
        setStep(1); // a details field is the problem -- surface it where it's shown
      } else {
        setError(validated.error.issues[0].message);
      }
      return;
    }
    mutate(validated.data);
  };

  return (
    <div className="shadow-input mx-auto w-full max-w-2xl rounded-none bg-card md:rounded-2xl">
      <div className="max-h-[80vh] overflow-y-auto p-4 md:p-8">
        <h2 className="text-xl font-bold text-foreground">Request a Dataset</h2>
        <p className="mt-2 max-w-md text-sm text-muted-foreground">
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
            <Alert variant="success">
              <CheckCircle2 />
              <AlertTitle>Request filed as issue #{result.issueNumber}</AlertTitle>
              <AlertDescription>
                <a
                  href={result.issueUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 hover:underline"
                >
                  Open the issue
                  <ArrowUpRight size={12} />
                </a>
              </AlertDescription>
            </Alert>
            <GradientButton type="button" onClick={onClose}>
              Done
            </GradientButton>
          </div>
        ) : (
          <form
            className="my-8"
            onSubmit={(event) => {
              event.preventDefault();
              if (step === 1) goToStep(2);
              else handleSubmit();
            }}
          >
            <Stepper value={step} onValueChange={goToStep} className="mb-6">
              <StepperNav>
                <StepperItem step={1} completed={step > 1}>
                  <StepperTrigger>
                    <StepperIndicator />
                    <StepperTitle>Details</StepperTitle>
                  </StepperTrigger>
                </StepperItem>
                <StepperSeparator />
                <StepperItem step={2}>
                  <StepperTrigger>
                    <StepperIndicator />
                    <StepperTitle>Analytics</StepperTitle>
                  </StepperTrigger>
                </StepperItem>
              </StepperNav>
            </Stepper>

            {step === 1 ? (
              <>
                <Field className="mb-4" data-invalid={!!fieldErrors.datasetId}>
                  <FieldLabel htmlFor="dr-dataset-id">Dataset ID</FieldLabel>
                  <Input
                    id="dr-dataset-id"
                    value={form.datasetId}
                    onChange={(event) =>
                      setForm((prev) => ({ ...prev, datasetId: event.target.value }))
                    }
                    aria-invalid={!!fieldErrors.datasetId}
                    placeholder="e.g. 2026-q2-comms-dump"
                  />
                  <FieldError errors={fieldErrors.datasetId?.map((message) => ({ message }))} />
                </Field>

                <Field className="mb-4" data-invalid={!!fieldErrors.name}>
                  <FieldLabel htmlFor="dr-name">
                    Name <span className="text-muted-foreground">(optional)</span>
                  </FieldLabel>
                  <Input
                    id="dr-name"
                    value={form.name}
                    onChange={(event) =>
                      setForm((prev) => ({ ...prev, name: event.target.value }))
                    }
                    aria-invalid={!!fieldErrors.name}
                    placeholder="Q2 Communications Dump"
                  />
                  <FieldError errors={fieldErrors.name?.map((message) => ({ message }))} />
                </Field>

                <Field className="mb-2" data-invalid={!!fieldErrors.reason}>
                  <FieldLabel htmlFor="dr-reason">Reason for request</FieldLabel>
                  <Textarea
                    id="dr-reason"
                    value={form.reason}
                    onChange={(event) =>
                      setForm((prev) => ({ ...prev, reason: event.target.value }))
                    }
                    aria-invalid={!!fieldErrors.reason}
                    placeholder="What is this dataset, where does it come from, and why is it needed?"
                    rows={4}
                  />
                  <FieldError errors={fieldErrors.reason?.map((message) => ({ message }))} />
                </Field>
              </>
            ) : (
              <div>
                <div className="mb-3 flex items-center gap-2">
                  <Sparkles size={14} className="text-annotation" />
                  <span className="text-sm font-medium text-foreground">Analytics to run</span>
                  <span className="ml-auto text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                    {enabledCount} selected
                  </span>
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
            )}

            {error && (
              <Alert variant="destructive" className="mt-4">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <div className="mt-6 flex gap-3">
              {step === 1 ? (
                <>
                  {onClose && (
                    <button
                      type="button"
                      onClick={onClose}
                      className="h-10 flex-1 rounded-md border border-border text-sm text-muted-foreground hover:text-foreground"
                    >
                      Cancel
                    </button>
                  )}
                  <GradientButton type="submit">
                    Next
                    <ArrowRight size={14} className="ml-1.5 inline" />
                  </GradientButton>
                </>
              ) : (
                <>
                  <button
                    type="button"
                    onClick={() => goToStep(1)}
                    className="inline-flex h-10 flex-1 items-center justify-center gap-1.5 rounded-md border border-border text-sm text-muted-foreground hover:text-foreground"
                  >
                    <ArrowLeft size={14} />
                    Back
                  </button>
                  <GradientButton type="submit" isLoading={isPending} loadingText="Filing…">
                    Submit Request →
                  </GradientButton>
                </>
              )}
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
