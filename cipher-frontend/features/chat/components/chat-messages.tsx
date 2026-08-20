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
import { MessageSquareIcon } from "lucide-react";
import { Fragment } from "react";
import type { ChatCitation } from "../types";
import { ChatMessageActions } from "./chat-message-actions";
import { Citations } from "./citations";

interface ChatMessagesProps {
  messages: UIMessage[];
  onRegenerate: () => void;
  /** Called when a citation card is clicked -- opens the cited file at that location. */
  onOpenCitation: (citation: ChatCitation) => void;
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
}: ChatMessagesProps) {
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
            const isAssistant = message.role === "assistant";

            return (
              <div key={message.id} className="flex w-full items-start gap-2">
                {isAssistant && (
                  <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center shrink-0 border text-xs font-medium">
                    AI
                  </div>
                )}
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

                      if (
                        toolLabel === "search_documents" &&
                        part.state === "output-available" &&
                        Array.isArray(part.output)
                      ) {
                        return (
                          <Citations
                            key={key}
                            citations={part.output as ChatCitation[]}
                            onOpen={onOpenCitation}
                          />
                        );
                      }

                      return (
                        <Tool key={key}>
                          {part.type === "dynamic-tool" ? (
                            <ToolHeader
                              type={part.type}
                              state={part.state}
                              toolName={part.toolName}
                            />
                          ) : (
                            <ToolHeader type={part.type} state={part.state} />
                          )}
                          <ToolContent>
                            {part.input != null &&
                              typeof part.input === "object" &&
                              Object.keys(part.input as object).length > 0 && (
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
                </div>
              </div>
            );
          })
        )}
      </ConversationContent>
      <ConversationScrollButton />
    </Conversation>
  );
}
