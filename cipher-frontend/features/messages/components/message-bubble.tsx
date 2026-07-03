"use client";
import { Check, Copy, Flag, Languages, Loader2 } from "lucide-react";
import { useReducer, useRef } from "react";
import type { Message } from "../types";

async function translateToEnglish(text: string): Promise<string> {
  await new Promise((r) => setTimeout(r, 600));
  return `[EN] ${text}`;
}

type MessageBubbleProps = {
  message: Message;
  isSender: boolean;
  showSender: boolean;
};

type State = {
  hovered: boolean;
  copied: boolean;
  flagged: boolean;
  translation: string | null;
  isTranslating: boolean;
  showTranslation: boolean;
};

type Action =
  | { type: "hover" }
  | { type: "unhover" }
  | { type: "copy" }
  | { type: "uncopy" }
  | { type: "toggleFlag" }
  | { type: "toggleTranslation" }
  | { type: "startTranslation" }
  | { type: "finishTranslation"; text: string };

const initialState: State = {
  hovered: false,
  copied: false,
  flagged: false,
  translation: null,
  isTranslating: false,
  showTranslation: false,
};

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "hover":
      return { ...state, hovered: true };
    case "unhover":
      return { ...state, hovered: false };
    case "copy":
      return { ...state, copied: true };
    case "uncopy":
      return { ...state, copied: false };
    case "toggleFlag":
      return { ...state, flagged: !state.flagged };
    case "toggleTranslation":
      return { ...state, showTranslation: !state.showTranslation };
    case "startTranslation":
      return { ...state, isTranslating: true, showTranslation: true };
    case "finishTranslation":
      return { ...state, isTranslating: false, translation: action.text };
    default:
      return state;
  }
}

export function MessageBubble({
  message,
  isSender,
  showSender,
}: MessageBubbleProps) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const { hovered, copied, flagged, translation, isTranslating, showTranslation } = state;
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleMouseEnter = () => {
    hoverTimer.current = setTimeout(() => dispatch({ type: "hover" }), 60);
  };
  const handleMouseLeave = () => {
    if (hoverTimer.current) clearTimeout(hoverTimer.current);
    dispatch({ type: "unhover" });
  };

  const handleCopy = async () => {
    if (!message.text) return;
    await navigator.clipboard.writeText(message.text).catch(() => {});
    dispatch({ type: "copy" });
    setTimeout(() => dispatch({ type: "uncopy" }), 1500);
  };

  const handleTranslate = async () => {
    if (!message.text) return;
    if (translation) {
      dispatch({ type: "toggleTranslation" });
      return;
    }
    dispatch({ type: "startTranslation" });
    const result = await translateToEnglish(message.text);
    dispatch({ type: "finishTranslation", text: result });
  };

  const isTranslated = showTranslation && !!translation;

  return (
    <div
      className={`flex w-full ${isSender ? "justify-end" : "justify-start"}`}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <div className="max-w-[85%]" style={{ minWidth: 0 }}>
        {showSender && (
          <div
            className={`flex items-center gap-2 px-1 mb-1 ${isSender ? "flex-row-reverse" : "flex-row"}`}
          >
            <span className="text-[10px] font-bold text-slate-600 tracking-tight">
              {message.sender}
            </span>
            <span className="text-[10px] text-slate-700">
              {message?.dateSent
                ? new Date(message.dateSent).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  })
                : ""}
            </span>
          </div>
        )}

        <div
          className={`flex items-end gap-1.5 ${isSender ? "flex-row-reverse" : "flex-row"}`}
        >
          <div className="relative">
            <div
              className={`px-5 py-3 rounded-2xl text-[13px] leading-relaxed shadow-lg transition-colors ${
                isSender
                  ? "bg-indigo-600 text-white rounded-tr-none"
                  : "bg-[#1c2128] text-slate-300 rounded-tl-none border border-slate-800/50"
              }`}
            >
              {isTranslated && (
                <div
                  className={`flex items-center gap-1 mb-1.5 ${isSender ? "justify-end" : "justify-start"}`}
                >
                  <Languages
                    size={10}
                    strokeWidth={2}
                    className={
                      isSender ? "text-indigo-300/70" : "text-slate-600"
                    }
                  />
                  <span
                    className={`text-[10px] font-medium ${isSender ? "text-indigo-300/70" : "text-slate-600"}`}
                  >
                    Translated to English
                  </span>
                </div>
              )}

              {showTranslation && isTranslating ? (
                <span
                  className={`flex items-center gap-1.5 ${isSender ? "text-indigo-200/60" : "text-slate-600"} italic`}
                >
                  <Loader2 size={11} className="animate-spin" />
                  Translating…
                </span>
              ) : isTranslated ? (
                translation
              ) : (
                message.text
              )}
            </div>
          </div>

          <div
            className={`flex items-center gap-0.5 transition-all duration-150 shrink-0 ${
              hovered
                ? "opacity-100 translate-y-0"
                : "opacity-0 translate-y-1 pointer-events-none"
            }`}
          >
            <ActionButton
              onClick={handleTranslate}
              active={showTranslation}
              title={showTranslation ? "Show original" : "Translate to English"}
            >
              <Languages size={12} strokeWidth={1.75} />
            </ActionButton>
            <ActionButton onClick={handleCopy} active={copied} title="Copy">
              {copied ? (
                <Check size={12} strokeWidth={2.5} />
              ) : (
                <Copy size={12} strokeWidth={1.75} />
              )}
            </ActionButton>
            <ActionButton
              onClick={() => dispatch({ type: "toggleFlag" })}
              active={flagged}
              title={flagged ? "Unflag" : "Flag"}
            >
              <Flag size={12} strokeWidth={1.75} />
            </ActionButton>
          </div>
        </div>
      </div>
    </div>
  );
}

function ActionButton({
  onClick,
  active,
  title,
  children,
}: {
  onClick: () => void;
  active?: boolean;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className={`flex items-center justify-center w-6 h-6 rounded-full border transition-all duration-150 ${
        active
          ? "bg-indigo-500/20 border-indigo-500/40 text-indigo-400"
          : "bg-slate-800/80 border-slate-700/50 text-slate-500 hover:text-slate-300 hover:border-slate-600"
      }`}
    >
      {children}
    </button>
  );
}
