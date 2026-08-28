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
import { MODELS, PROVIDER_LABELS } from "@/features/chat/lib/models";
import { useMe } from "@/features/users/hooks/use-me";
import { getInitials } from "@/features/users/utils";
import { Layers, Settings as SettingsIcon, Sparkles, UserRound } from "lucide-react";

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
  const { model, keys, setModel, setKey } = useChatStore();
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
                {MODELS.filter((m) => m.provider === p).map((m) => (
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
            <div key={p} className="space-y-1.5">
              <Label>{label} API key</Label>
              <Input
                type="password"
                placeholder={`Enter ${label} key...`}
                value={keys[p] ?? ""}
                onChange={(e) => setKey(p, e.target.value)}
                className="max-w-sm"
              />
            </div>
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

function PreferencesSection() {
  return (
    <SectionCard
      icon={Layers}
      title="Preferences"
      description="Defaults for browsing and triage. Coming soon."
    >
      <p className="text-sm text-muted-foreground">
        Per-viewer defaults (pagination mode, annotation visibility, results
        density) will live here once they&apos;re backed by a shared preferences
        store.
      </p>
    </SectionCard>
  );
}

export default function SettingsPage() {
  return (
    <div className="max-w-3xl mx-auto px-6 relative pb-20">
      <PageHeader
        eyebrow="Account"
        value="Settings"
        icon={<SettingsIcon className="h-3.5 w-3.5 text-primary/80" />}
      />

      <div className="mt-6 space-y-6">
        <ProfileSection />
        <ModelSection />
        <PreferencesSection />
      </div>
    </div>
  );
}
