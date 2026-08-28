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
import { Fragment } from "react";
import { describeToolCall } from "../lib/tool-labels";
import { summarizeToolPayload } from "../lib/summarize-tool-payload";
import type { ChatCitation } from "../types";
import { AssistantAvatar } from "./assistant-avatar";
import { ChatMessageActions } from "./chat-message-actions";
import { Citations } from "./citations";
import { ThinkingIndicator } from "./thinking-indicator";

/** A tool output is a citation list if it's a non-empty array of citation-shaped objects. */
function asCitationList(output: unknown): ChatCitation[] | null {
  if (!Array.isArray(output) || output.length === 0) return null;
  const first = output[0];
  if (typeof first !== "object" || first === null) return null;
  if (!("displayName" in first) || !("kind" in first)) return null;
  return output as ChatCitation[];
}

interface ChatMessagesProps {
  messages: UIMessage[];
  onRegenerate: () => void;
  /** Called when a citation card is clicked -- opens the cited file at that location. */
  onOpenCitation: (citation: ChatCitation) => void;
  /** Renders the "thinking" indicator at the end of the thread. */
  showThinking?: boolean;
}

function isToolPart(
  part: UIMessagePart<UIDataTypes, UITools>
): part is ToolPart {
  return part.type === "dynamic-tool" || part.type.startsWith("tool-");
}

export function ChatMessages({
  messages,
  onRegenerate,
  onOpenCitation,
  showThinking = false,
}: ChatMessagesProps) {
  if (messages.length === 0 && !showThinking) {
    return (
      <Conversation>
        <ConversationContent>
          <ConversationEmptyState
            icon={
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-linear-to-br from-primary to-purple-600 text-white shadow-[0_0_20px_rgba(99,102,241,0.35)]">
                <SparklesIcon className="h-6 w-6" />
              </div>
            }
            title="Ask Cipher anything"
            description="Ask questions across your datasets in plain language. Answers stay grounded in retrieved sources, with citations you can open."
          />
        </ConversationContent>
      </Conversation>
    );
  }

  return (
    <Conversation>
      <ConversationContent>
        {messages.map((message, messageIndex) => {
          const isLast = messageIndex === messages.length - 1;
          const isAssistant = message.role === "assistant";

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
                      <Fragment key={key}>
                        <Message from={message.role}>
                          <MessageContent>
                            <MessageResponse>{part.text}</MessageResponse>
                          </MessageContent>
                        </Message>
                        {message.role === "assistant" && isLast && (
                          <ChatMessageActions
                            text={part.text}
                            onRegenerate={onRegenerate}
                          />
                        )}
                      </Fragment>
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

                    if (part.state === "output-available") {
                      const citations = asCitationList(part.output);
                      if (citations) {
                        return (
                          <Citations
                            key={key}
                            citations={citations}
                            onOpen={onOpenCitation}
                          />
                        );
                      }
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
                                ? summarizeToolPayload(part.output)
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
              </div>
            </div>
          );
        })}
        {showThinking && (
          <div className="flex w-full items-start">
            <ThinkingIndicator />
          </div>
        )}
      </ConversationContent>
      <ConversationScrollButton />
    </Conversation>
  );
}
