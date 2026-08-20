"use client";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/page-header";
import type { IconComponent } from "@/types/common";
import {
  HelpCircle,
  MessageSquare,
  Search as SearchIcon,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useMemo, useState } from "react";

interface FaqEntry {
  question: string;
  answer: string;
}

interface FaqCategory {
  title: string;
  icon: IconComponent;
  items: FaqEntry[];
}

const CATEGORIES: FaqCategory[] = [
  {
    title: "Getting started",
    icon: Sparkles,
    items: [
      {
        question: "What is Cipher?",
        answer:
          "Cipher helps you triage an unknown set of data -- messages, images, emails, documents -- into defined schemas so it becomes searchable, with AI/ML doing the first pass of enrichment (embeddings, classification, extraction) and you confirming or correcting it.",
      },
      {
        question: "What's the difference between a Dataset and a Viewer?",
        answer:
          "A Dataset is a named ingest of raw source data. Viewers (Images, Faces, Persons, and friends) are the schema-specific screens for exploring what was triaged out of one or more datasets -- create a dataset first, then browse its contents from the matching viewer.",
      },
      {
        question: "Where do I start with a new batch of data?",
        answer:
          "Create a dataset from the Datasets page and give it a descriptive name. Cipher runs file-type detection, extraction, and embedding automatically, then routes records into the matching viewers as processing completes.",
      },
    ],
  },
  {
    title: "Search & triage",
    icon: SearchIcon,
    items: [
      {
        question: "What's the difference between text, semantic, and hybrid search?",
        answer:
          "Text search matches keywords directly. Semantic search embeds your query and finds conceptually similar records, even without exact word overlap. Hybrid blends both, which is the best default for messy, unstructured data.",
      },
      {
        question: "What does the amber highlighting mean?",
        answer:
          "Amber marks anything AI/ML-generated -- auto-detected faces, model-suggested labels, extracted fields -- so it's visually distinct from data a person entered or confirmed. Cyan is used for search-relevance highlights instead.",
      },
      {
        question: "Can I search by image or face similarity?",
        answer:
          "Yes. The Images and Faces viewers support similarity search -- upload or select a reference image and Cipher ranks the rest of the corpus by embedding distance.",
      },
      {
        question: "Paginated vs. infinite scroll -- which should I use?",
        answer:
          "Both are supported on most list views via a toggle in the page header. Infinite scroll is faster for casual browsing; paginated view is easier when you need a stable page number to return to.",
      },
    ],
  },
  {
    title: "Chat & models",
    icon: MessageSquare,
    items: [
      {
        question: "Which model providers can I chat with?",
        answer:
          "OpenAI, Anthropic, and Google models are supported with your own API key, plus a local model that runs against a vLLM server on your machine with no key required. Switch providers any time from the model picker in Chat or the sidebar.",
      },
      {
        question: "Where are my API keys stored?",
        answer:
          "Locally in your browser only, keyed by provider. They're sent to the backend per-request to authenticate that call and are never persisted server-side.",
      },
      {
        question: "Can I scope a chat to one dataset?",
        answer:
          "Yes -- pick a dataset from the selector in the chat input to restrict retrieval to that dataset's records instead of the whole corpus.",
      },
    ],
  },
  {
    title: "Data & privacy",
    icon: ShieldCheck,
    items: [
      {
        question: "Does Cipher send my data anywhere besides the model provider?",
        answer:
          "No. Search, extraction, and embedding all run against your own backend and datastores. The only outbound calls are chat completions to whichever model provider you've configured, using your own key.",
      },
      {
        question: "Can I delete a dataset once it's ingested?",
        answer:
          "Yes, from the dataset's detail page. Deleting a dataset removes its records from every viewer that surfaced them.",
      },
    ],
  },
];

function normalize(value: string): string {
  return value.toLowerCase();
}

export default function FaqPage() {
  const [query, setQuery] = useState("");

  const filteredCategories = useMemo(() => {
    const q = normalize(query.trim());
    if (!q) return CATEGORIES;

    return CATEGORIES.map((category) => ({
      ...category,
      items: category.items.filter(
        (item) =>
          normalize(item.question).includes(q) ||
          normalize(item.answer).includes(q)
      ),
    })).filter((category) => category.items.length > 0);
  }, [query]);

  return (
    <div className="max-w-4xl mx-auto px-6 relative pb-20">
      <PageHeader
        eyebrow="Help"
        value="Frequently Asked Questions"
        icon={<HelpCircle className="h-3.5 w-3.5 text-indigo-400/80" />}
      />

      <div className="mt-6 mb-10">
        <Input
          placeholder="Search the FAQ..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="max-w-md"
        />
      </div>

      {filteredCategories.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No questions match &ldquo;{query}&rdquo;.
        </p>
      ) : (
        <div className="space-y-10">
          {filteredCategories.map((category) => (
            <section key={category.title}>
              <div className="flex items-center gap-2 mb-2 text-slate-200">
                <category.icon className="h-4 w-4 text-indigo-400" />
                <h2 className="text-sm font-semibold tracking-wide uppercase">
                  {category.title}
                </h2>
              </div>
              <Accordion type="multiple" className="rounded-lg border border-slate-800 bg-sidebar/40 px-4">
                {category.items.map((item) => (
                  <AccordionItem key={item.question} value={item.question}>
                    <AccordionTrigger className="text-slate-200">
                      {item.question}
                    </AccordionTrigger>
                    <AccordionContent>{item.answer}</AccordionContent>
                  </AccordionItem>
                ))}
              </Accordion>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
