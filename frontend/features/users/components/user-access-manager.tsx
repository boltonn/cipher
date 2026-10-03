"use client";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { SearchBarShell } from "@/components/search-bar-shell";
import { SearchInput } from "@/components/search-input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { DatasetMultiSelectCombobox } from "@/features/datasets/components/dataset-multi-select-combobox";
import { cn } from "@/lib/utils";
import { Search, ShieldCheck, Trash2, UserPlus } from "lucide-react";
import { useState } from "react";
import { useMe } from "../hooks/use-me";
import {
  useCreateUser,
  useDeleteUser,
  useSetUserDatasets,
  useUpdateUser,
  useUserDatasetIds,
  useUsers,
} from "../hooks/use-users";
import type { User, UserCreate } from "../types";
import { getInitials } from "../utils";

const EMPTY_USER: UserCreate = { name: "", email: "" };

function AddUserForm() {
  const [draft, setDraft] = useState<UserCreate>(EMPTY_USER);
  const createUser = useCreateUser(() => setDraft(EMPTY_USER));
  const canSubmit =
    draft.name.trim() && draft.email.trim() && !createUser.isPending;

  return (
    <form
      className="flex items-end gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (canSubmit)
          createUser.mutate({
            name: draft.name.trim(),
            email: draft.email.trim(),
          });
      }}
    >
      <div className="flex-1 space-y-1.5">
        <Label htmlFor="new-user-name">Name</Label>
        <Input
          id="new-user-name"
          autoComplete="off"
          value={draft.name}
          onChange={(e) => setDraft({ ...draft, name: e.target.value })}
        />
      </div>
      <div className="flex-1 space-y-1.5">
        <Label htmlFor="new-user-email">Email</Label>
        <Input
          id="new-user-email"
          type="email"
          autoComplete="off"
          value={draft.email}
          onChange={(e) => setDraft({ ...draft, email: e.target.value })}
        />
      </div>
      <Button
        type="submit"
        size="sm"
        className="h-9 gap-1.5"
        disabled={!canSubmit}
      >
        <UserPlus size={14} />
        Add
      </Button>
    </form>
  );
}

/** One user's admin flag and dataset memberships; keyed by user id so the draft resets per user. */
function UserAccessEditor({ user, isSelf }: { user: User; isSelf: boolean }) {
  const { data: savedIds, isPending } = useUserDatasetIds(user.id);
  const [draftIds, setDraftIds] = useState<string[] | null>(null);
  const setDatasets = useSetUserDatasets(user.id);
  const updateUser = useUpdateUser(user.id);
  const deleteUser = useDeleteUser();

  const datasetIds = draftIds ?? savedIds ?? [];
  const isDirty = draftIds !== null;

  return (
    <div className="space-y-4 rounded-lg border border-border/60 p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-foreground">
            {user.name}
          </p>
          <p className="truncate text-xs text-muted-foreground">{user.email}</p>
        </div>
        {!isSelf && (
          <ConfirmDialog
            trigger={
              <Button
                variant="ghost"
                size="icon"
                aria-label="Delete user"
                className="h-8 w-8 text-muted-foreground/70 hover:bg-destructive/10 hover:text-destructive"
              >
                <Trash2 size={14} />
              </Button>
            }
            title={`Delete ${user.name}?`}
            description="They lose access to every dataset. Their past reviews stay, unattributed."
            confirmLabel="Delete User"
            isPending={deleteUser.isPending}
            onConfirm={() => deleteUser.mutate(user.id)}
          />
        )}
      </div>

      <div className="flex items-center justify-between gap-3">
        <div>
          <Label htmlFor={`admin-${user.id}`}>Admin</Label>
          <p className="text-xs text-muted-foreground">
            Sees every dataset and manages users.
          </p>
        </div>
        <Switch
          id={`admin-${user.id}`}
          checked={user.isAdmin}
          disabled={isSelf || updateUser.isPending}
          onCheckedChange={(isAdmin) => updateUser.mutate({ isAdmin })}
        />
      </div>

      <div className="space-y-1.5">
        <Label>Dataset access</Label>
        {user.isAdmin && (
          <p className="text-xs text-muted-foreground">
            Admins already see every dataset.
          </p>
        )}
        <DatasetMultiSelectCombobox
          value={datasetIds}
          onChange={setDraftIds}
          placeholder={isPending ? "Loading…" : "Add datasets…"}
        />
        <div className="flex justify-end gap-2 pt-1">
          <Button
            variant="ghost"
            size="sm"
            disabled={!isDirty}
            onClick={() => setDraftIds(null)}
          >
            Reset
          </Button>
          <Button
            size="sm"
            disabled={!isDirty || setDatasets.isPending}
            onClick={() =>
              setDatasets.mutate(datasetIds, {
                onSuccess: () => setDraftIds(null),
              })
            }
          >
            Save access
          </Button>
        </div>
      </div>
    </div>
  );
}

/** Admin: find a user, then set whether they're an admin and which datasets they can access. */
export function UserAccessManager() {
  const { data: me } = useMe();
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { data, isFetching, hasNextPage, fetchNextPage, isFetchingNextPage } =
    useUsers({
      query: query || undefined,
    });
  const users = data?.pages.flatMap((page) => page.data) ?? [];
  const selected = users.find((u) => u.id === selectedId);

  return (
    <div className="space-y-4">
      <SearchBarShell
        isActive={isFetching}
        icon={<Search size={16} strokeWidth={1.5} />}
      >
        <SearchInput
          value={query}
          onSearch={setQuery}
          ariaLabel="Search users"
          placeholder="Search by name or email…"
        />
      </SearchBarShell>

      <div className="max-h-72 divide-y divide-border/50 overflow-y-auto rounded-lg border border-border/60">
        {users.map((user) => (
          <button
            key={user.id}
            type="button"
            onClick={() => setSelectedId(user.id)}
            className={cn(
              "flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-muted/40",
              user.id === selectedId && "bg-primary/10"
            )}
          >
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted text-[11px] font-semibold">
              {getInitials(user.name)}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm text-foreground">
                {user.name}
              </span>
              <span className="block truncate text-xs text-muted-foreground">
                {user.email}
              </span>
            </span>
            {user.isAdmin && (
              <Badge className="gap-1 border-none bg-primary/10 text-[11px] text-primary">
                <ShieldCheck size={11} />
                Admin
              </Badge>
            )}
          </button>
        ))}
        {!isFetching && users.length === 0 && (
          <p className="px-3 py-4 text-center text-xs text-muted-foreground">
            No users found
          </p>
        )}
        {hasNextPage && (
          <Button
            variant="ghost"
            size="sm"
            className="w-full rounded-none text-xs"
            disabled={isFetchingNextPage}
            onClick={() => fetchNextPage()}
          >
            Load more
          </Button>
        )}
      </div>

      {selected && (
        <UserAccessEditor
          key={selected.id}
          user={selected}
          isSelf={selected.id === me?.id}
        />
      )}

      <AddUserForm />
    </div>
  );
}
