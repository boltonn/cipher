"use client";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { SidebarMenuButton, SidebarMenuItem } from "@/components/ui/sidebar";
import { useChatStore } from "@/features/chat/hooks/use-chat-store";
import { useModelOptions } from "@/features/chat/hooks/use-model-options";
import { PROVIDER_LABELS } from "@/features/chat/lib/models";
import { Sparkles } from "lucide-react";

export function SidebarModelSwitcher() {
  const { model: storedModel, setModel } = useChatStore();
  const { options, labelFor, effectiveModel } = useModelOptions();
  const model = effectiveModel(storedModel);
  const currentLabel = labelFor(model);

  return (
    <SidebarMenuItem>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <SidebarMenuButton
            tooltip={`Model: ${currentLabel}`}
            className="
              relative h-12 overflow-hidden transition-all duration-300 ease-out
              group/button cursor-pointer my-0.5 text-muted-foreground
              hover:border-2 hover:border-primary hover:bg-primary/10
              group-data-[collapsible=icon]:size-12! group-data-[collapsible=icon]:p-0!
              group-data-[collapsible=icon]:justify-center
            "
          >
            <Sparkles
              className="h-6 w-6 shrink-0 ml-2 text-muted-foreground group-hover/button:text-foreground group-data-[collapsible=icon]:ml-0"
            />
            <span className="truncate group-data-[collapsible=icon]:hidden">
              Model
            </span>
          </SidebarMenuButton>
        </DropdownMenuTrigger>

        <DropdownMenuContent side="right" align="end" className="w-56">
          <DropdownMenuRadioGroup value={model} onValueChange={setModel}>
            {Object.keys(PROVIDER_LABELS).map((provider) => (
              <div key={provider}>
                <DropdownMenuLabel>
                  {PROVIDER_LABELS[provider]}
                </DropdownMenuLabel>
                {options.filter((m) => m.provider === provider).map((m) => (
                  <DropdownMenuRadioItem key={m.id} value={m.id}>
                    {m.label}
                  </DropdownMenuRadioItem>
                ))}
              </div>
            ))}
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenu>
    </SidebarMenuItem>
  );
}
