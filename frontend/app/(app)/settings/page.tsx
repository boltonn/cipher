"use client";

import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { useChatStore } from "@/features/chat/hooks/use-chat-store";
import { useModelOptions } from "@/features/chat/hooks/use-model-options";
import { PROVIDER_LABELS } from "@/features/chat/lib/models";
import { useMe } from "@/features/users/hooks/use-me";
import { getInitials } from "@/features/users/utils";
import {
  Check,
  Eye,
  EyeOff,
  Layers,
  Settings as SettingsIcon,
  Sparkles,
  UserRound,
} from "lucide-react";
import { useState } from "react";

function ApiKeyField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (next: string) => void;
}) {
  const [revealed, setRevealed] = useState(false);
  const hasKey = value.trim().length > 0;

  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2">
        <Label>{label} API key</Label>
        {hasKey && (
          <span className="inline-flex items-center gap-1 text-[10px] font-medium text-emerald-500">
            <Check size={11} />
            Saved in this browser
          </span>
        )}
      </div>
      <div className="relative max-w-sm">
        <Input
          type={revealed ? "text" : "password"}
          placeholder={`Enter ${label} key…`}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="pr-9"
        />
        {hasKey && (
          <button
            type="button"
            onClick={() => setRevealed((v) => !v)}
            aria-label={revealed ? "Hide key" : "Show key"}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          >
            {revealed ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
        )}
      </div>
    </div>
  );
}

function SectionCard({
  icon: Icon,
  title,
  description,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-primary" />
          <CardTitle>{title}</CardTitle>
        </div>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">{children}</CardContent>
    </Card>
  );
}

function ProfileSection() {
  const { data: user, isLoading } = useMe();

  return (
    <SectionCard
      icon={UserRound}
      title="Profile"
      description="Your account details, managed outside of Cipher."
    >
      <div className="flex items-center gap-4">
        <div className="h-12 w-12 rounded-full bg-linear-to-br from-primary to-purple-600 flex items-center justify-center text-sm font-semibold text-white shadow-[0_0_10px_rgba(99,102,241,0.3)] shrink-0">
          {isLoading ? "" : getInitials(user?.name)}
        </div>
        <div className="min-w-0">
          <p className="text-sm font-medium text-foreground truncate">
            {isLoading ? "Loading..." : user?.name || "Unknown User"}
          </p>
          <p className="text-xs text-muted-foreground truncate">
            {isLoading ? "" : user?.email || "No email linked"}
          </p>
        </div>
      </div>
    </SectionCard>
  );
}

function ModelSection() {
  const { model: storedModel, keys, setModel, setKey } = useChatStore();
  const { options, effectiveModel } = useModelOptions();
  const model = effectiveModel(storedModel);
  const provider = model.split(":")[0];

  return (
    <SectionCard
      icon={Sparkles}
      title="Model & API keys"
      description="Choose the default model used in Chat and store per-provider API keys locally in this browser."
    >
      <div className="space-y-1.5">
        <Label>Default model</Label>
        <Select value={model} onValueChange={setModel}>
          <SelectTrigger className="max-w-sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {Object.keys(PROVIDER_LABELS).map((p) => (
              <div key={p}>
                <p className="px-2 pt-2 pb-1 text-xs font-medium text-muted-foreground">
                  {PROVIDER_LABELS[p]}
                </p>
                {options.filter((m) => m.provider === p).map((m) => (
                  <SelectItem key={m.id} value={m.id}>
                    {m.label}
                  </SelectItem>
                ))}
              </div>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Separator />

      <div className="space-y-3">
        {Object.entries(PROVIDER_LABELS)
          .filter(([p]) => p !== "local")
          .map(([p, label]) => (
            <ApiKeyField
              key={p}
              label={label}
              value={keys[p] ?? ""}
              onChange={(next) => setKey(p, next)}
            />
          ))}
        <p className="text-xs text-muted-foreground">
          Keys are stored locally in your browser and only sent with your own
          chat requests. The <span className="text-foreground">{PROVIDER_LABELS[provider]}</span>{" "}
          key is used for the default model above.
        </p>
      </div>
    </SectionCard>
  );
}

const PREFERENCE_PREVIEW = [
  { label: "Pagination", value: "Infinite scroll" },
  { label: "Annotation visibility", value: "Show AI/ML marks" },
  { label: "Results density", value: "Comfortable" },
] as const;

function PreferencesSection() {
  return (
    <SectionCard
      icon={Layers}
      title="Preferences"
      description="Per-viewer defaults for browsing and triage."
    >
      <div className="flex items-center gap-2">
        <span className="rounded-full border border-border bg-muted/40 px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
          Coming soon
        </span>
        <span className="text-xs text-muted-foreground">
          Preview — these will be editable once a shared preferences store lands.
        </span>
      </div>
      <div className="divide-y divide-border/50 rounded-lg border border-border/60 opacity-60">
        {PREFERENCE_PREVIEW.map((row) => (
          <div
            key={row.label}
            className="flex items-center justify-between px-3 py-2.5 text-sm"
          >
            <span className="text-muted-foreground">{row.label}</span>
            <span className="font-medium text-foreground">{row.value}</span>
          </div>
        ))}
      </div>
    </SectionCard>
  );
}

export default function SettingsPage() {
  return (
    <div className="max-w-400 mx-auto px-6 relative pb-20 pt-5">
      <PageHeader
        eyebrow="Account"
        value="Settings"
        icon={<SettingsIcon className="h-3.5 w-3.5 text-primary/80" />}
      />

      <div className="w-full max-w-2xl space-y-6">
        <ProfileSection />
        <ModelSection />
        <PreferencesSection />
      </div>
    </div>
  );
}
