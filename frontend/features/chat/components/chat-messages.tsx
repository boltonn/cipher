"use client";

import {
  Confirmation,
  ConfirmationRequest,
  ConfirmationTitle,
} from "@/components/ai-elements/confirmation";
import {
  Conversation,
  ConversationContent,
  ConversationEmptyState,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import {
  Message,
  MessageContent,
  MessageResponse,
} from "@/components/ai-elements/message";
import {
  Reasoning,
  ReasoningContent,
  ReasoningTrigger,
} from "@/components/ai-elements/reasoning";
import {
  Source,
  Sources,
  SourcesContent,
  SourcesTrigger,
} from "@/components/ai-elements/sources";
import {
  Tool,
  ToolContent,
  ToolHeader,
  ToolInput,
  ToolOutput,
  type ToolPart,
} from "@/components/ai-elements/tool";
import type { UIMessage, UIMessagePart, UIDataTypes, UITools } from "ai";
import { SparklesIcon } from "lucide-react";
import { describeToolCall } from "../lib/tool-labels";
import { summarizeToolPayload } from "../lib/summarize-tool-payload";
import type { ChatCitation } from "../types";
import { AssistantAvatar } from "./assistant-avatar";
import { ChatMessageActions } from "./chat-message-actions";
import { Citations } from "./citations";
import { ThinkingIndicator } from "./thinking-indicator";

/** A tool output is a citation list if it's a non-empty array of citation-shaped objects,
 * or an object carrying one under `citations` (e.g. `count_emails` totals + people). */
function asCitationList(output: unknown): ChatCitation[] | null {
  if (typeof output === "object" && output !== null && "citations" in output) {
    return asCitationList(output.citations);
  }
  if (!Array.isArray(output) || output.length === 0) return null;
  const first = output[0];
  if (typeof first !== "object" || first === null) return null;
  if (!("displayName" in first) || !("kind" in first)) return null;
  return output as ChatCitation[];
}

/** A tool's output for its trace card. Citation lists (already shown as the message's
 * Sources) collapse to a count + names instead of their full JSON. */
function summarizeToolOutput(output: unknown): unknown {
  const citations = asCitationList(output);
  if (!citations) return summarizeToolPayload(output);
  const sources = citations.map((c) => c.displayName);
  if (Array.isArray(output)) return { results: citations.length, sources };
  const rest = Object.fromEntries(
    Object.entries(output as Record<string, unknown>).filter(([key]) => key !== "citations")
  );
  return { ...(summarizeToolPayload(rest) as object), results: citations.length, sources };
}

interface ChatMessagesProps {
  messages: UIMessage[];
  onRegenerate: () => void;
  /** Called when a citation card is clicked -- opens the cited file at that location. */
  onOpenCitation: (citation: ChatCitation) => void;
  /** Renders the "thinking" indicator at the end of the thread. */
  showThinking?: boolean;
  /** Send one of the starter prompts shown on the empty thread. */
  onExamplePrompt?: (text: string) => void;
}

const EXAMPLE_PROMPTS = [
  "Summarize what this dataset contains.",
  "Who are the people mentioned most often?",
  "Find messages about travel or meetings.",
];

function isToolPart(
  part: UIMessagePart<UIDataTypes, UITools>
): part is ToolPart {
  return part.type === "dynamic-tool" || part.type.startsWith("tool-");
}

/** Tools whose citations are lookup candidates, not evidence -- shown only when nothing else cited. */
const LOOKUP_TOOLS = new Set(["find_entity"]);

function toolName(part: ToolPart): string {
  return part.type === "dynamic-tool" ? part.toolName : part.type.replace(/^tool-/, "");
}

/** Every citation the message's tool calls returned, de-duplicated, in call order. */
function collectCitations(message: UIMessage): ChatCitation[] {
  const toolParts = message.parts.filter(
    (part): part is ToolPart => isToolPart(part) && part.state === "output-available"
  );
  const hasEvidence = toolParts.some(
    (part) => !LOOKUP_TOOLS.has(toolName(part)) && asCitationList(part.output)
  );
  const seen = new Set<string>();
  const out: ChatCitation[] = [];
  for (const part of toolParts) {
    if (hasEvidence && LOOKUP_TOOLS.has(toolName(part))) continue;
    const list = asCitationList(part.output);
    if (!list) continue;
    for (const citation of list) {
      const key =
        citation.chunkId ?? citation.targetId ?? `${citation.kind}:${citation.displayName}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(citation);
    }
  }
  return out;
}

export function ChatMessages({
  messages,
  onRegenerate,
  onOpenCitation,
  showThinking = false,
  onExamplePrompt,
}: ChatMessagesProps) {
  if (messages.length === 0 && !showThinking) {
    return (
      <Conversation className="h-full">
        <ConversationContent className="mx-auto w-full max-w-3xl px-4 py-6">
          <ConversationEmptyState
            icon={
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-linear-to-br from-primary to-purple-600 text-white">
                <SparklesIcon className="h-6 w-6" />
              </div>
            }
            title="Ask Cipher anything"
            description="Ask questions across your datasets in plain language. Answers stay grounded in retrieved sources, with citations you can open."
          />
          {onExamplePrompt && (
            <div className="mx-auto mt-5 flex max-w-md flex-wrap justify-center gap-2">
              {EXAMPLE_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => onExamplePrompt(prompt)}
                  className="rounded-full border border-border bg-muted/40 px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
                >
                  {prompt}
                </button>
              ))}
            </div>
          )}
        </ConversationContent>
      </Conversation>
    );
  }

  return (
    <Conversation className="h-full">
      <ConversationContent className="mx-auto w-full max-w-3xl px-4 py-6">
        {messages.map((message, messageIndex) => {
          const isLast = messageIndex === messages.length - 1;
          const isAssistant = message.role === "assistant";

          const assistantText = isAssistant
            ? message.parts
                .flatMap((part) => (part.type === "text" ? [part.text] : []))
                .join("\n\n")
            : "";
          const citations = isAssistant ? collectCitations(message) : [];

          return (
            <div key={message.id} className="flex w-full items-start gap-3">
              {isAssistant && <AssistantAvatar />}
              <div className="flex min-w-0 flex-1 flex-col gap-2">
                {message.parts.map((part, i) => {
                  const key = `${message.id}-${i}`;

                  if (part.type === "reasoning") {
                    return (
                      <Reasoning key={key}>
                        <ReasoningTrigger />
                        <ReasoningContent>{part.text}</ReasoningContent>
                      </Reasoning>
                    );
                  }

                  if (part.type === "source-url") {
                    return (
                      <Sources key={key}>
                        <SourcesTrigger count={1} />
                        <SourcesContent>
                          <Source href={part.url}>
                            {part.title ?? part.url}
                          </Source>
                        </SourcesContent>
                      </Sources>
                    );
                  }

                  if (part.type === "text") {
                    return (
                      <Message key={key} from={message.role}>
                        <MessageContent>
                          <MessageResponse>{part.text}</MessageResponse>
                        </MessageContent>
                      </Message>
                    );
                  }

                  if (isToolPart(part)) {
                    const toolLabel =
                      part.type === "dynamic-tool"
                        ? part.toolName
                        : part.type.replace(/^tool-/, "");

                    if (part.state === "approval-requested") {
                      return (
                        <Confirmation
                          key={key}
                          state={part.state}
                          approval={part.approval}
                        >
                          <ConfirmationRequest>
                            <ConfirmationTitle>
                              {toolLabel} needs approval
                            </ConfirmationTitle>
                          </ConfirmationRequest>
                        </Confirmation>
                      );
                    }

                    const toolTitle = describeToolCall(
                      toolLabel,
                      "input" in part ? part.input : undefined
                    );

                    return (
                      <Tool key={key}>
                        {part.type === "dynamic-tool" ? (
                          <ToolHeader
                            type={part.type}
                            state={part.state}
                            toolName={part.toolName}
                            title={toolTitle}
                          />
                        ) : (
                          <ToolHeader
                            type={part.type}
                            state={part.state}
                            title={toolTitle}
                          />
                        )}
                        <ToolContent>
                          {part.input != null &&
                            typeof part.input === "object" &&
                            Object.keys(part.input as object).length > 0 && (
                              <ToolInput
                                input={summarizeToolPayload(part.input)}
                              />
                            )}
                          <ToolOutput
                            output={
                              "output" in part
                                ? summarizeToolOutput(part.output)
                                : undefined
                            }
                            errorText={part.errorText}
                          />
                        </ToolContent>
                      </Tool>
                    );
                  }

                  return null;
                })}

                {isAssistant && assistantText && (
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-2 pt-1">
                    {isLast && (
                      <ChatMessageActions
                        text={assistantText}
                        onRegenerate={onRegenerate}
                      />
                    )}
                    {citations.length > 0 && (
                      <Citations citations={citations} onOpen={onOpenCitation} />
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        })}
        {showThinking && <ThinkingIndicator />}
      </ConversationContent>
      <ConversationScrollButton />
    </Conversation>
  );
}
