# CIPHER

CIPHER is a project to help a user triage an unknown set of data into defined schemas for search with AI/ML enhancement. 



## Python backend (cipher)

This is a UV workspace monorepo for a AI/ML based data triage platform.

### Workspace layout

```bash
analytics/     # ML analytics services (each independently deployable)
  clir/        # Multilingual text embedding (Jina model)
  filetyper/   # File type detection (Google Magika + heuristics)
  pykreuzberg/ # Rust-based text extraction & OCR
  pyparse/     # Email/document parsing (eml, msg, vcf, docx, prd, etc.)
  setfitcv/    # Image embedding and classification via CLIP
backend/       # FastAPI REST API (entry: cipher-serve)
packages/
  cipher-orchestration # Combining analytics applied to data ingestion into a datastore with CLI utilities
  cipher-datastores/  # DB layer: PostgreSQL (pgvector) + Elasticsearch
  cipher-schemas/     # Pydantic v2 models shared across all services
  cipher-utils/       # FastAPI, AWS, or other general utilities applicable to backend or multiple services
```

### Design Principles / Preferences

* Everything is typed
* Pydantic first particularly where validation is required
  * datetime fields should start with date_
  * use default= instead of something implicit like None
  * use str over UUID types for IDs
* the majority of time prefer keyword arguments in function use
* Google doc strings
* minimal comments (prefer well named variables and functions)
* leverage core packages as much as possible for seperation of concerns
* python 3.12 syntax to lowercase list, use | instead of Optional, etc.
* each feature should be able to used as a stand-alone (ie. fastapi analytic services)
* orchestration can be standalone scripts that are easy to use until an orchestation architecture is designed from the ground up
* consistent terminology between schemas, tables, etc. with the frontend where appropriate besides casing
* if you need to test a new feature with fake data always create a new dataset and name appropriately
* keep code brief

## Frontend (cipher-frontend)

This a NextJS for triaging the data.

### Workspace layout

```bash
app/  # NextJS app layout with pages
components/  # Core components used across the app
backend/     # FastAPI REST API (entry: cipher-serve)
features/    # feature based layout where everything aligns with a specific view or schema (commonly aligns with core package schema)
  datasets/     # Dataset (ie. example of a feature)
    components/    # Dataset specific components
        dataset-create-form.tsx
        datasets-table.tsx
    hooks/
        use-create-datasets.ts   # Wraps React Query logic (fetch/mutation) in custom hook
    api.ts     # fetching logic / endpoint from the backend
    types.ts   # dataset specific types that again match to core schemas 
  emails/
  images/
hooks/      # common hooks
lib/        # common utils and api client logic for axios
provider/   # common providers at the app level
types/      # common schemas
```


### Tech Stack

* NextJS / React
* React Query
* ShadCN
* TailwindCSS v4
* AI SDK
* Typescript
* Zod
* TanStack Virtual (especially for tables)

### Design Principles / Preferences

* prefer client-side fetching and management
* useEffect is anti-pattern
* prefer typescript objects that align with pydantic schemas (but camelCase), rather than many pieces of useState, especially for things like filters
* use react doctor to make code performant
* keep most data out of the URL unless its an ID specific page
* search / filter text inputs commit on Enter (and blur), never on every keystroke -- use the shared `SearchInput` (`components/search-input.tsx`), no debounced-refetch-as-you-type
* never rely on native HTML autocomplete / `datalist` for suggestion-driven fields (browser autofill covers the menu); use the `Autocomplete` primitive (`components/ui/autocomplete.tsx`) -- cmdk + portaled popover, free-text value, opts out of autofill
* Annotation for AI/ML should be a first-class citizen but should be denoted with a specific color
* consistent terminology with the backend where appropriate with the exception of casing per above
* support both paginated and infinite scroll for most things