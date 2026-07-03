# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
npm run dev      # Start dev server (localhost:3000)
npm run build    # Production build
npm run lint     # ESLint check
```

No test suite is configured.

## Architecture

This is a **Next.js 16 (App Router)** frontend for "Cipher" / "Cipher" — a tool for searching and exploring unstructured data (messages, images, emails, datasets, documents). It connects to a FastAPI backend at `http://localhost:8000/api`.

### Directory layout

- `app/` — Next.js pages: `chat`, `datasets`, `emails`, `images`, `messages`. Each page imports from its corresponding `features/` folder.
- `features/<domain>/` — Self-contained feature slices, each with:
  - `api.ts` — axios service object wrapping `apiClient`
  - `types.ts` — TypeScript interfaces for the domain
  - `components/` — React components specific to that feature
  - `hooks/` — Feature-specific hooks (often React Query or Zustand)
- `components/ui/` — shadcn/ui primitives plus custom viewers (PDF, DOCX, XLSX, CSV).
- `components/ai-elements/` — Custom AI chat UI primitives: `Conversation`, `Message`, `PromptInput`, etc. These wrap Vercel AI SDK's `useChat` hook.
- `lib/apiClient.ts` — Single axios instance; base URL is `NEXT_PUBLIC_API_URL` or `/api` (proxied in prod, direct to `:8000` in dev).
- `providers/` — `ReactQueryProvider` (TanStack Query) and `ThemeProvider` (next-themes, dark by default).
- `hooks/` — Shared hooks: `use-debounce`, `use-mobile`.
- `types/common.ts` — Shared TypeScript types.

### Key patterns

**API calls**: All HTTP calls go through `apiClient` from `lib/apiClient.ts`. Feature services are plain objects (e.g. `imagesService`, `messagesService`) — no class instances.

**State management**: Zustand for client-side persistent state (e.g. `useChatStore` persists API keys and selected model to localStorage under key `chat-config`). TanStack Query for server state and caching.

**Chat feature**: Uses Vercel AI SDK (`@ai-sdk/react` + `ai` package). `useChat` is wired to `http://localhost:8000/api/chat`. The `DefaultChatTransport` sends `model` in the body and the provider API key in `x-api-key` header. The chat store holds keys keyed by provider name (e.g. `openai`) extracted from the model string (`"openai:gpt-4o-mini"`).

**Styling**: Tailwind CSS v4 with a dark, deep-space aesthetic (`bg-[#050507]`, indigo accent colors). `cn()` utility from `lib/utils.ts` for conditional class merging.

**Path alias**: `@/` maps to the project root (configured in `tsconfig.json`).

### Backend contract

The FastAPI backend exposes REST endpoints under `/api`:
- `/api/images` — image search (text, similarity, upload)
- `/api/messages` — message/conversation search (text, semantic, hybrid)
- `/api/datasets` — dataset listing
- `/api/chat` — streaming chat (Vercel AI SDK protocol)
- `/api/users/me` — current user info

In development, Next.js image optimization proxies are set up for `localhost:8000`.