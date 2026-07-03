"use client";

import {
  Confirmation,
  ConfirmationRequest,
  ConfirmationTitle,
} from "@/components/ai-elements/confirmation";
import { EnvironmentVariables } from "@/components/ai-elements/environment-variables";
import { FileTree } from "@/components/ai-elements/file-tree";
import { InlineCitation } from "@/components/ai-elements/inline-citation";
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
import type { UIMessage } from "ai";
import { MessageSquareIcon } from "lucide-react";
import { Fragment } from "react";
import { ChatMessageActions } from "./chat-message-actions";

// Available part renderers — activate when backend sends these part types
const _partRenderers = { EnvironmentVariables, FileTree, InlineCitation } as const;

interface ChatMessagesProps {
  messages: UIMessage[];
  onRegenerate: () => void;
}

function isToolPart(part: unknown): part is {
  type: `tool-${string}`;
  toolCallId: string;
  state: ToolPart["state"];
  input?: Record<string, unknown>;
  output?: unknown;
  errorText?: string;
} {
  if (typeof part !== "object" || part === null) return false;
  const record = part as Record<string, unknown>;
  return (
    typeof record.type === "string" &&
    record.type.startsWith("tool-") &&
    "state" in record
  );
}

export function ChatMessages({ messages, onRegenerate }: ChatMessagesProps) {
  return (
    <Conversation>
      <ConversationContent>
        {messages.length === 0 ? (
          <ConversationEmptyState
            icon={<MessageSquareIcon className="size-12" />}
            title="Start a conversation"
            description="Ask anything to get started."
          />
        ) : (
          messages.map((message, messageIndex) => {
            const isLast = messageIndex === messages.length - 1;

            return (
              <Fragment key={message.id}>
                {message.parts.map((part, i) => {
                  const key = `${message.id}-${i}`;

                  if (part.type === "reasoning") {
                    return (
                      <Reasoning key={key}>
                        <ReasoningTrigger />
                        <ReasoningContent>{part.reasoning}</ReasoningContent>
                      </Reasoning>
                    );
                  }

                  if (part.type === "source") {
                    const { source } = part as {
                      type: "source";
                      source: { url: string; title?: string };
                    };
                    return (
                      <Sources key={key}>
                        <SourcesTrigger count={1} />
                        <SourcesContent>
                          <Source href={source.url}>
                            {source.title ?? source.url}
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
                    if (part.state === "approval-requested") {
                      return (
                        <Confirmation key={key}>
                          <ConfirmationRequest>
                            <ConfirmationTitle>
                              {part.type.replace(/^tool-/, "")} needs approval
                            </ConfirmationTitle>
                          </ConfirmationRequest>
                        </Confirmation>
                      );
                    }

                    return (
                      <Tool key={key}>
                        <ToolHeader
                          type={part.type as ToolPart["type"]}
                          state={part.state}
                        />
                        <ToolContent>
                          {part.input != null &&
                            Object.keys(part.input).length > 0 && (
                              <ToolInput input={part.input} />
                            )}
                          <ToolOutput
                            output={part.output}
                            errorText={part.errorText}
                          />
                        </ToolContent>
                      </Tool>
                    );
                  }

                  return null;
                })}
              </Fragment>
            );
          })
        )}
      </ConversationContent>
      <ConversationScrollButton />
    </Conversation>
  );
}
