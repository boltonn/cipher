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
import { Button } from "@/components/ui/button";
import { ButtonGroup } from "@/components/ui/button-group";
import { Switch } from "@/components/ui/switch";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Textarea } from "@/components/ui/textarea";
import {
  ANALYTICS,
  analyticLabel,
  datasetRequestSchema,
  dependentsOf,
  paramSchemas,
  withPrerequisites,
  type AnalyticDef,
  type DatasetRequestResult,
  type EnrichmentType,
} from "@/features/datasets/request-types";
import {
  useDatasetRequestConfig,
  useRequestDataset,
} from "@/features/datasets/hooks/use-request-dataset";
import { cn } from "@/lib/utils";
import {
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  CheckCircle2,
  Info,
  Lock,
  OctagonAlert,
  Sparkles,
} from "lucide-react";
import { useMemo, useState } from "react";

const detailsSchema = datasetRequestSchema.pick({
  name: true,
  datasetId: true,
  description: true,
});

interface DatasetRequestFormProps {
  /** Called when the user dismisses the form (cancel, or done after success). */
  onClose?: () => void;
}

type ParamValues = Record<string, string>;

interface FormState {
  name: string;
  datasetId: string;
  description: string;
  analytics: Record<string, { enabled: boolean; params: ParamValues }>;
}

function buildInitialState(): FormState {
  return {
    name: "",
    datasetId: "",
    description: "",
    analytics: Object.fromEntries(
      ANALYTICS.map((analytic) => [
        analytic.type,
        {
          enabled: false,
          params: Object.fromEntries(
            analytic.params.map((param) => [
              param.key,
              String(param.defaultValue ?? ""),
            ])
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
    name?: string[];
    datasetId?: string[];
    description?: string[];
  }>({});
  const [result, setResult] = useState<DatasetRequestResult | null>(null);

  const { data: config } = useDatasetRequestConfig();
  const { mutate, isPending } = useRequestDataset(setResult);

  const enabledCount = ANALYTICS.filter(
    (a) => form.analytics[a.type].enabled
  ).length;

  /**
   * Analytics that are only on because something enabled depends on them, mapped
   * to the labels of those dependents. Their toggle is locked while any dependent
   * is on -- turning a dependent off releases the lock.
   */
  const lockedBy = useMemo(() => {
    const map = new Map<EnrichmentType, string[]>();
    for (const a of ANALYTICS) {
      if (!form.analytics[a.type].enabled) continue;
      for (const dep of withPrerequisites(a.type)) {
        if (dep === a.type) continue;
        map.set(dep, [...(map.get(dep) ?? []), a.label]);
      }
    }
    return map;
  }, [form.analytics]);

  /** Validate the step-1 fields; on failure populate `fieldErrors` and stay put. */
  const validateDetails = () => {
    const parsed = detailsSchema.safeParse({
      name: form.name,
      datasetId: form.datasetId,
      description: form.description || undefined,
    });
    if (parsed.success) {
      setFieldErrors({});
      return true;
    }
    const fe = parsed.error.flatten().fieldErrors;
    setFieldErrors({
      name: fe.name,
      datasetId: fe.datasetId,
      description: fe.description,
    });
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

  /** Toggling an analytic cascades: turning it on also turns on everything it
   *  depends on; turning it off also turns off everything that depends on it. */
  const toggleAnalytic = (type: EnrichmentType, enabled: boolean) =>
    setForm((prev) => {
      const affected = enabled ? withPrerequisites(type) : dependentsOf(type);
      const analytics = { ...prev.analytics };
      for (const t of [type, ...affected]) {
        analytics[t] = { ...analytics[t], enabled };
      }
      return { ...prev, analytics };
    });

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
        bucket[param.key] =
          param.kind === "number"
            ? Number(value)
            : param.kind === "groups" && !param.csv
              ? value.split(",").filter(Boolean)
              : param.kind === "boolean"
                ? value === "true"
                : value;
      }

      for (const emitType of def.emits ?? [def.type]) {
        const parsed = paramSchemas[emitType].safeParse(
          rawByOwner[emitType] ?? {}
        );
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
      name: form.name,
      datasetId: form.datasetId,
      description: form.description || undefined,
      analytics,
    });
    if (!validated.success) {
      const fe = validated.error.flatten().fieldErrors;
      setFieldErrors({
        name: fe.name,
        datasetId: fe.datasetId,
        description: fe.description,
      });
      if (fe.name?.length || fe.datasetId?.length || fe.description?.length) {
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
          File a request to ingest a dataset. This opens a GitHub issue
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

        {config && !config.configured && (
          <Alert variant="destructive" className="mt-3">
            <OctagonAlert />
            <AlertDescription>
              Dataset requests aren&apos;t set up on this server (no GitHub
              integration configured) -- filing will fail.
            </AlertDescription>
          </Alert>
        )}

        {result ? (
          <div className="my-8 space-y-4">
            <Alert variant="success">
              <CheckCircle2 />
              <AlertTitle>
                Request filed as issue #{result.issueNumber}
              </AlertTitle>
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
                <Field className="mb-4" data-invalid={!!fieldErrors.name}>
                  <FieldLabel htmlFor="dr-name">Name</FieldLabel>
                  <Input
                    id="dr-name"
                    value={form.name}
                    onChange={(event) =>
                      setForm((prev) => ({ ...prev, name: event.target.value }))
                    }
                    aria-invalid={!!fieldErrors.name}
                    placeholder="Q2 Communications Dump"
                  />
                  <FieldError
                    errors={fieldErrors.name?.map((message) => ({ message }))}
                  />
                </Field>

                <Field className="mb-4" data-invalid={!!fieldErrors.datasetId}>
                  <FieldLabel htmlFor="dr-dataset-id">Dataset ID</FieldLabel>
                  <Input
                    id="dr-dataset-id"
                    value={form.datasetId}
                    onChange={(event) =>
                      setForm((prev) => ({
                        ...prev,
                        datasetId: event.target.value,
                      }))
                    }
                    aria-invalid={!!fieldErrors.datasetId}
                    placeholder="e.g. 2026-q2-comms-dump"
                  />
                  <FieldError
                    errors={fieldErrors.datasetId?.map((message) => ({
                      message,
                    }))}
                  />
                </Field>

                <Field
                  className="mb-2"
                  data-invalid={!!fieldErrors.description}
                >
                  <FieldLabel htmlFor="dr-description">
                    Description{" "}
                    <span className="text-muted-foreground">(optional)</span>
                  </FieldLabel>
                  <Textarea
                    id="dr-description"
                    value={form.description}
                    onChange={(event) =>
                      setForm((prev) => ({
                        ...prev,
                        description: event.target.value,
                      }))
                    }
                    aria-invalid={!!fieldErrors.description}
                    placeholder="What is this dataset and where does it come from? (optional)"
                    rows={4}
                  />
                  <FieldError
                    errors={fieldErrors.description?.map((message) => ({
                      message,
                    }))}
                  />
                </Field>
              </>
            ) : (
              <div>
                <div className="mb-1 flex items-center gap-2">
                  <Sparkles size={14} className="text-annotation" />
                  <span className="text-sm font-medium text-foreground">
                    Analytics you&apos;ll want
                  </span>
                  <span className="ml-auto text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
                    {enabledCount} selected
                  </span>
                </div>
                <p className="mb-3 text-xs text-muted-foreground">
                  A wishlist for whoever ingests this dataset -- not a run
                  trigger. Time estimates appear on the dataset&apos;s page once
                  it&apos;s staged.
                </p>

                <div className="space-y-2">
                  {ANALYTICS.map((analytic) => (
                    <AnalyticRow
                      key={analytic.type}
                      analytic={analytic}
                      enabled={form.analytics[analytic.type].enabled}
                      values={form.analytics[analytic.type].params}
                      lockedBy={lockedBy.get(analytic.type)}
                      onToggle={(enabled) =>
                        toggleAnalytic(analytic.type, enabled)
                      }
                      onParamChange={(key, value) =>
                        setParam(analytic.type, key, value)
                      }
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

            <div className="mt-6 flex items-center gap-3">
              {step === 1 ? (
                <>
                  {onClose && (
                    <Button
                      type="button"
                      variant="outline"
                      onClick={onClose}
                      className="h-10 flex-1"
                    >
                      Cancel
                    </Button>
                  )}
                  <GradientButton type="submit" className="flex-1">
                    Next
                    <ArrowRight size={14} className="ml-1.5 inline" />
                  </GradientButton>
                </>
              ) : (
                <>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => goToStep(1)}
                    className="h-10 flex-1"
                  >
                    <ArrowLeft size={14} className="mr-1.5" />
                    Back
                  </Button>
                  <GradientButton
                    type="submit"
                    isLoading={isPending}
                    loadingText="Filing…"
                    disabled={config ? !config.configured : false}
                    className="flex-1"
                  >
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
  /** Labels of enabled analytics that depend on this one, if any -- locks the toggle on. */
  lockedBy?: string[];
  onToggle: (enabled: boolean) => void;
  onParamChange: (key: string, value: string) => void;
}

function AnalyticRow({
  analytic,
  enabled,
  values,
  lockedBy,
  onToggle,
  onParamChange,
}: AnalyticRowProps) {
  const locked = !!lockedBy?.length;

  return (
    <div
      className={cn(
        "rounded-lg border px-3 py-2.5 transition-colors",
        enabled
          ? "border-annotation/40 bg-annotation/5"
          : "border-border bg-muted/30"
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm text-foreground">{analytic.label}</p>
          <p className="text-xs text-muted-foreground">
            {analytic.description}
          </p>
          {analytic.dependsOn && analytic.dependsOn.length > 0 && (
            <p className="mt-0.5 text-[11px] text-muted-foreground/70">
              Needs {analytic.dependsOn.map(analyticLabel).join(", ")} --
              included automatically
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {locked && (
            <span
              className="text-muted-foreground"
              title={`Required by ${lockedBy.join(", ")}`}
            >
              <Lock size={11} />
            </span>
          )}
          <Switch
            checked={enabled}
            onCheckedChange={onToggle}
            disabled={locked}
            aria-label={analytic.label}
          />
        </div>
      </div>

      {enabled && analytic.params.length > 0 && (
        <div className="mt-3 grid grid-cols-2 gap-3 border-t border-border/60 pt-3">
          {analytic.params.map((param) => {
            const value = values[param.key] ?? "";
            const missing = !param.optional && value.trim() === "";
            return (
              <div key={param.key} className="flex flex-col space-y-1">
                <div className="flex items-center gap-1">
                  <Label
                    htmlFor={`${analytic.type}-${param.key}`}
                    className="text-xs text-muted-foreground"
                  >
                    {param.label}
                    {param.optional && " (optional)"}
                  </Label>
                  {param.info && <InfoHint text={param.info} />}
                </div>
                {param.kind === "boolean" ? (
                  <div className="flex h-8 items-center">
                    <Switch
                      id={`${analytic.type}-${param.key}`}
                      checked={value === "true"}
                      onCheckedChange={(checked) =>
                        onParamChange(param.key, String(checked))
                      }
                    />
                  </div>
                ) : param.kind === "groups" ? (
                  <GroupToggles
                    value={values[param.key] ?? String(param.defaultValue)}
                    options={param.options ?? []}
                    onChange={(next) => onParamChange(param.key, next)}
                  />
                ) : param.kind === "select" ? (
                  <Select
                    value={values[param.key] || String(param.defaultValue)}
                    onValueChange={(value) => onParamChange(param.key, value)}
                  >
                    <SelectTrigger
                      id={`${analytic.type}-${param.key}`}
                      className="h-8 text-xs"
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {param.options?.map((option) => (
                        <SelectItem
                          key={option}
                          value={option}
                          className="text-xs"
                        >
                          {param.optionLabels?.[option] ?? option}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <Input
                    id={`${analytic.type}-${param.key}`}
                    type={param.kind === "number" ? "number" : "text"}
                    value={value}
                    min={param.min}
                    max={param.max}
                    step={param.step}
                    placeholder={param.optional ? "default" : undefined}
                    aria-invalid={missing}
                    onChange={(event) =>
                      onParamChange(param.key, event.target.value)
                    }
                    className="h-8 text-xs"
                  />
                )}
                {missing && (
                  <span className="text-[11px] text-destructive">Required</span>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function InfoHint({ text }: { text: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label="What is this?"
          className="text-muted-foreground/60 transition-colors hover:text-foreground"
        >
          <Info size={11} />
        </button>
      </TooltipTrigger>
      <TooltipContent className="max-w-64 text-xs leading-relaxed">
        {text}
      </TooltipContent>
    </Tooltip>
  );
}

/** Pick filetype groups as toggles; the value is comma-joined like every other param string. */
function GroupToggles({
  value,
  options,
  onChange,
}: {
  value: string;
  options: readonly string[];
  onChange: (value: string) => void;
}) {
  const selected = new Set(value.split(",").filter(Boolean));
  const toggle = (option: string) => {
    const next = new Set(selected);
    if (next.has(option)) next.delete(option);
    else next.add(option);
    onChange(options.filter((o) => next.has(o)).join(","));
  };
  return (
    <ButtonGroup>
      {options.map((option) => (
        <Button
          key={option}
          type="button"
          variant="outline"
          size="sm"
          aria-pressed={selected.has(option)}
          onClick={() => toggle(option)}
          className={cn(
            "h-8 border-border text-xs",
            selected.has(option)
              ? "bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary"
              : "bg-muted/40 text-muted-foreground hover:text-foreground"
          )}
        >
          {option}
        </Button>
      ))}
    </ButtonGroup>
  );
}
