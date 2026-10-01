"use client";

import * as React from "react";
import { Command as CommandPrimitive } from "cmdk";

import { Popover, PopoverAnchor, PopoverContent } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { Check, Loader2 } from "lucide-react";

/**
 * Free-text input with a suggestion dropdown -- like a combobox, but the value
 * is whatever the user types; suggestions only assist. Use this instead of a
 * bare `<input>` with `list=`/native autofill whenever the field offers its own
 * suggestions: the browser's autofill dropdown covers or fights a custom menu,
 * so the input here opts out of it (`autoComplete="off"` + the password-manager
 * ignore attrs) and we render the menu ourselves.
 *
 * Built on cmdk (keyboard nav, highlight) + a Radix popover (portaled, so the
 * menu escapes `overflow` containers). Server-driven by default
 * (`shouldFilter={false}`) -- filter the `items` yourself, or pass
 * `shouldFilter` to let cmdk match client-side.
 *
 * @example
 * <Autocomplete>
 *   <AutocompleteInput value={q} onValueChange={setQ} onEnter={() => search(q)} placeholder="Search names..." />
 *   <AutocompleteContent isLoading={isFetching}>
 *     {people.map((p) => (
 *       <AutocompleteItem key={p.id} value={p.name} onSelect={() => pick(p)}>
 *         {p.name}
 *       </AutocompleteItem>
 *     ))}
 *   </AutocompleteContent>
 * </Autocomplete>
 */

interface AutocompleteContextValue {
  open: boolean;
  setOpen: (open: boolean) => void;
  disabled: boolean;
  anchorRef: React.RefObject<HTMLDivElement | null>;
  inputRef: React.RefObject<HTMLInputElement | null>;
}

const AutocompleteContext = React.createContext<AutocompleteContextValue | null>(null);

function useAutocomplete() {
  const ctx = React.useContext(AutocompleteContext);
  if (!ctx) throw new Error("Autocomplete parts must be used within <Autocomplete>");
  return ctx;
}

interface AutocompleteProps extends React.ComponentProps<typeof CommandPrimitive> {
  /** Controlled open state of the suggestion menu. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  defaultOpen?: boolean;
  disabled?: boolean;
}

function Autocomplete({
  open: openProp,
  onOpenChange,
  defaultOpen = false,
  disabled = false,
  shouldFilter = false,
  className,
  ...props
}: AutocompleteProps) {
  const [openState, setOpenState] = React.useState(defaultOpen);
  const open = openProp ?? openState;
  const anchorRef = React.useRef<HTMLDivElement | null>(null);
  const inputRef = React.useRef<HTMLInputElement | null>(null);

  const setOpen = React.useCallback(
    (next: boolean) => {
      if (disabled) return;
      setOpenState(next);
      onOpenChange?.(next);
    },
    [disabled, onOpenChange]
  );

  return (
    <AutocompleteContext.Provider value={{ open, setOpen, disabled, anchorRef, inputRef }}>
      <Popover open={open} onOpenChange={setOpen}>
        <CommandPrimitive
          data-slot="autocomplete"
          shouldFilter={shouldFilter}
          className={cn("w-full overflow-visible bg-transparent", className)}
          {...props}
        />
      </Popover>
    </AutocompleteContext.Provider>
  );
}

interface AutocompleteInputProps
  extends Omit<React.ComponentProps<typeof CommandPrimitive.Input>, "value" | "onChange"> {
  value: string;
  onValueChange: (value: string) => void;
  /** Fired on Enter when no suggestion is highlighted -- lets this double as a search field. */
  onEnter?: (value: string) => void;
}

function AutocompleteInput({
  className,
  value,
  onValueChange,
  onEnter,
  onFocus,
  onBlur,
  onKeyDown,
  ...props
}: AutocompleteInputProps) {
  const { open, setOpen, disabled, anchorRef, inputRef } = useAutocomplete();

  return (
    <PopoverAnchor asChild>
      <div
        ref={anchorRef}
        // Clicks on the padding/addons land on the wrapper -- route focus to the input.
        onMouseDown={(e) => {
          if (e.target === inputRef.current || disabled) return;
          e.preventDefault();
          inputRef.current?.focus();
        }}
        className={cn(
          "group/autocomplete flex h-10 w-full items-center gap-2 text-sm rounded-lg border border-border bg-muted/40 px-3 py-2 transition duration-300 focus-within:ring-2 focus-within:ring-primary/50",
          disabled && "cursor-not-allowed opacity-50",
          className
        )}
      >
        <CommandPrimitive.Input
          ref={inputRef}
          data-slot="autocomplete-input"
          value={value}
          onValueChange={onValueChange}
          disabled={disabled}
          // Opt out of native autofill / password-manager overlays -- they
          // cover and hijack the custom suggestion menu.
          autoComplete="off"
          autoCorrect="off"
          autoCapitalize="none"
          spellCheck={false}
          data-1p-ignore=""
          data-lpignore="true"
          data-bwignore=""
          data-form-type="other"
          onFocus={(e) => {
            setOpen(true);
            onFocus?.(e);
          }}
          onBlur={(e) => {
            // Keep open if focus moved into the menu (item click); the popover's
            // outside-interaction handler covers real dismissals.
            if (!anchorRef.current?.contains(e.relatedTarget as Node)) setOpen(false);
            onBlur?.(e);
          }}
          onKeyDown={(e) => {
            onKeyDown?.(e);
            if (e.defaultPrevented) return;
            if (e.key === "Escape") {
              setOpen(false);
            } else if (e.key === "Enter" && onEnter) {
              // If cmdk has a highlighted suggestion it will fire that item's
              // onSelect for this Enter -- so the free-text handler only runs
              // when nothing is highlighted (or the menu is closed).
              const hasActive =
                open &&
                document.querySelector("[data-slot=autocomplete-content] [cmdk-item][aria-selected=true]");
              if (!hasActive) onEnter(value);
            } else if (!open && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
              setOpen(true);
            }
          }}
          className={cn(
            "h-full min-w-0 flex-1 bg-transparent text-foreground outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed"
          )}
          {...props}
        />
      </div>
    </PopoverAnchor>
  );
}

interface AutocompleteContentProps
  extends React.ComponentProps<typeof CommandPrimitive.List> {
  isLoading?: boolean;
  emptyMessage?: string;
  /** Popover sizing/placement passthroughs. */
  align?: React.ComponentProps<typeof PopoverContent>["align"];
  sideOffset?: number;
}

function AutocompleteContent({
  className,
  children,
  isLoading = false,
  emptyMessage = "No results",
  align = "start",
  sideOffset = 6,
  ...props
}: AutocompleteContentProps) {
  const { anchorRef } = useAutocomplete();

  return (
    <PopoverContent
      data-slot="autocomplete-content"
      align={align}
      sideOffset={sideOffset}
      onOpenAutoFocus={(e) => e.preventDefault()}
      onCloseAutoFocus={(e) => e.preventDefault()}
      onInteractOutside={(e) => {
        // Clicks/focus on the input itself must not dismiss the menu.
        if (anchorRef.current?.contains(e.target as Node)) e.preventDefault();
      }}
      className="w-(--radix-popover-trigger-width) min-w-56 p-0"
    >
      <CommandPrimitive.List
        className={cn(
          "no-scrollbar max-h-72 overflow-x-hidden overflow-y-auto overscroll-contain p-1",
          className
        )}
        {...props}
      >
        {isLoading ? (
          <div className="flex items-center justify-center gap-2 py-6 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            Searching...
          </div>
        ) : (
          <CommandPrimitive.Empty className="py-6 text-center text-sm text-muted-foreground">
            {emptyMessage}
          </CommandPrimitive.Empty>
        )}
        {children}
      </CommandPrimitive.List>
    </PopoverContent>
  );
}

function AutocompleteGroup({
  className,
  ...props
}: React.ComponentProps<typeof CommandPrimitive.Group>) {
  return (
    <CommandPrimitive.Group
      data-slot="autocomplete-group"
      className={cn(
        "overflow-hidden p-1 text-foreground **:[[cmdk-group-heading]]:px-2 **:[[cmdk-group-heading]]:py-1.5 **:[[cmdk-group-heading]]:text-xs **:[[cmdk-group-heading]]:font-medium **:[[cmdk-group-heading]]:text-muted-foreground",
        className
      )}
      {...props}
    />
  );
}

function AutocompleteSeparator({
  className,
  ...props
}: React.ComponentProps<typeof CommandPrimitive.Separator>) {
  return (
    <CommandPrimitive.Separator
      data-slot="autocomplete-separator"
      className={cn("-mx-1 my-1 h-px bg-border", className)}
      {...props}
    />
  );
}

interface AutocompleteItemProps
  extends React.ComponentProps<typeof CommandPrimitive.Item> {
  /** Show a check on the right (single-select style). */
  selected?: boolean;
}

function AutocompleteItem({
  className,
  children,
  selected,
  onSelect,
  ...props
}: AutocompleteItemProps) {
  const { setOpen } = useAutocomplete();

  return (
    <CommandPrimitive.Item
      data-slot="autocomplete-item"
      // Stop the input from blurring before onSelect lands.
      onMouseDown={(e) => e.preventDefault()}
      onSelect={(value) => {
        onSelect?.(value);
        setOpen(false);
      }}
      className={cn(
        "relative flex cursor-pointer items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-hidden select-none",
        "data-[disabled=true]:pointer-events-none data-[disabled=true]:opacity-50",
        "data-[selected=true]:bg-muted data-[selected=true]:text-foreground",
        "[&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        className
      )}
      {...props}
    >
      {children}
      {selected != null && (
        <Check className={cn("ml-auto size-4", selected ? "opacity-100" : "opacity-0")} />
      )}
    </CommandPrimitive.Item>
  );
}

export {
  Autocomplete,
  AutocompleteInput,
  AutocompleteContent,
  AutocompleteGroup,
  AutocompleteItem,
  AutocompleteSeparator,
};
