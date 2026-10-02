"use client";

import { TagsInput } from "@/components/tags-input";
import { Badge } from "@/components/ui/badge";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import {
  Ban,
  Calendar,
  Check,
  Copy,
  Maximize2,
  Search,
  Sparkles,
  Tag,
} from "lucide-react";
import Image from "next/image";
import { useState } from "react";
import { imagesService, useUpdateImageTags } from "../api";
import { ImagePublic, ImageSimilarityResult } from "../types";

interface ImageCardProps {
  image: ImagePublic | ImageSimilarityResult;
  onFindSimilar?: (id: string) => void;
  onExpand?: (image: ImagePublic) => void;
  /** Tags the grid is filtered to: their rejected / predicted state is shown on the card. */
  reviewTags?: string[];
  isSelected?: boolean;
  /** Something in the grid is selected: a click toggles selection instead of expanding. */
  isSelectionActive?: boolean;
  onToggleSelect?: (image: ImagePublic, range: boolean) => void;
}

export const ImageCard: React.FC<ImageCardProps> = ({
  image,
  onFindSimilar,
  onExpand,
  reviewTags,
  isSelected,
  isSelectionActive,
  onToggleSelect,
}) => {
  const [copied, setCopied] = useState(false);
  const activate = (range: boolean) => {
    if (onToggleSelect && (isSelectionActive || range))
      onToggleSelect(image, range);
    else onExpand?.(image);
  };
  // Of the filtered tags: the ones this image is explicitly not, and the ones a
  // model predicted that nobody has labelled yet.
  const rejectedTags = (reviewTags ?? []).filter((tag) =>
    image.negativeTags.includes(tag)
  );
  const predictedTags = (reviewTags ?? []).filter(
    (tag) =>
      tag in image.tagScores &&
      !image.tags.includes(tag) &&
      !image.negativeTags.includes(tag)
  );
  const imageUrl = imagesService.getImageUrl(image.id);
  const visibleTags = image.tags.slice(0, 3);
  const remainingCount = image.tags.length - visibleTags.length;
  const isEmbedded = !!image.embeddingModel;
  const similarityScore = "similarityScore" in image ? image.similarityScore : undefined;

  const handleCopyId = (e?: React.MouseEvent<HTMLButtonElement>) => {
    e?.stopPropagation();
    navigator.clipboard.writeText(image.id);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <TooltipProvider>
      <div
        className={cn(
          "group relative rounded-xl overflow-hidden bg-muted/40 border border-border/50 transition-all duration-300 hover:border-primary/40 hover:bg-muted/60",
          isSelected && "border-primary ring-2 ring-primary/40"
        )}
      >
        {/* Flush Image Container */}
        <div
          role="button"
          tabIndex={0}
          aria-pressed={isSelectionActive ? !!isSelected : undefined}
          className="aspect-4/5 relative w-full bg-background cursor-pointer"
          onClick={(e) => activate(e.shiftKey)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              activate(e.shiftKey);
            }
          }}
        >
          <Image
            src={imageUrl}
            alt={image.id}
            fill
            unoptimized
            loading="eager"
            className="object-cover transition-transform duration-500 group-hover:scale-105"
            sizes="(max-width: 768px) 100vw, (max-width: 1200px) 50vw, 33vw"
          />

          {onToggleSelect && (
            <button
              type="button"
              aria-label={isSelected ? "Deselect image" : "Select image"}
              onClick={(e) => {
                e.stopPropagation();
                onToggleSelect(image, e.shiftKey);
              }}
              className={cn(
                "absolute top-2 right-2 z-10 flex size-5 items-center justify-center rounded-md border transition-opacity",
                isSelected
                  ? "bg-primary border-primary text-primary-foreground opacity-100"
                  : "bg-background/80 border-border text-transparent opacity-0 group-hover:opacity-100",
                isSelectionActive && "opacity-100"
              )}
            >
              <Check size={12} strokeWidth={3} />
            </button>
          )}

          {/* Action Bar */}
          <div className="absolute inset-x-0 bottom-4 flex justify-center opacity-0 group-hover:opacity-100 translate-y-2 group-hover:translate-y-0 transition-all duration-300 z-10">
            <div
              className="flex items-center gap-4 bg-popover/95 border border-border px-4 py-2 rounded-full shadow-2xl"
              onClick={(e) => e.stopPropagation()} // Prevent card click when clicking bar
              onKeyDown={(e) => e.stopPropagation()}
            >
              <NavAction
                icon={<Search size={18} />}
                label="Find Similar"
                disabled={!isEmbedded}
                disabledLabel="Image hasn't been embedded yet"
                onClick={() => onFindSimilar?.(image.id)}
              />
              <TagPopoverAction image={image} />
              <NavAction
                icon={<Maximize2 size={18} />}
                label="Expand"
                onClick={() => onExpand?.(image)}
              />
              <NavAction
                icon={
                  copied ? (
                    <Check size={18} className="text-primary" />
                  ) : (
                    <Copy size={18} />
                  )
                }
                label={copied ? "Copied!" : "Copy ID"}
                onClick={handleCopyId}
              />
            </div>
          </div>

          {similarityScore != null && (
            <span className="absolute top-2 left-2 text-[11px] font-mono font-bold text-primary bg-primary/10 border border-primary/30 px-1.5 py-0.5 rounded backdrop-blur-sm">
              {(similarityScore * 100).toFixed(0)}% match
            </span>
          )}
        </div>

        {/* Footer */}
        <div className="p-3 border-t border-border/50 space-y-2">
          <div className="flex justify-between items-center h-4">
            {image.dateTaken && (
              <div className="flex items-center gap-1.5 text-muted-foreground">
                <Calendar size={10} className="text-primary/70" />
                <span className="text-[11px] font-bold uppercase tracking-wide">
                  {new Date(image.dateTaken).toLocaleDateString()}
                </span>
              </div>
            )}
          </div>
          <div className="flex flex-wrap gap-1">
            {predictedTags.map((tag) => (
              <Badge
                key={tag}
                className="bg-annotation/10 text-annotation text-[11px] border-none px-1.5 py-0 uppercase font-bold tracking-tight gap-1"
              >
                <Sparkles size={10} className="shrink-0" />
                {tag} {(image.tagScores[tag] * 100).toFixed(0)}%
              </Badge>
            ))}
            {rejectedTags.map((tag) => (
              <Badge
                key={tag}
                className="bg-destructive/10 text-destructive text-[11px] border-none px-1.5 py-0 uppercase font-bold tracking-tight gap-1"
              >
                <Ban size={10} className="shrink-0" />
                Not {tag}
              </Badge>
            ))}
            {visibleTags.map((tag) => (
              <Badge
                key={tag}
                className="bg-primary/10 text-primary text-[11px] border-none px-1.5 py-0 uppercase font-bold tracking-tight"
              >
                {tag}
              </Badge>
            ))}
            {remainingCount > 0 && (
              <span className="text-[11px] text-muted-foreground font-bold ml-1">
                +{remainingCount}
              </span>
            )}
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
};

const NavAction = ({
  icon,
  label,
  onClick,
  disabled,
  disabledLabel,
}: {
  icon: React.ReactNode;
  label: string;
  onClick?: (e?: React.MouseEvent<HTMLButtonElement>) => void;
  disabled?: boolean;
  disabledLabel?: string;
}) => (
  <Tooltip delayDuration={0}>
    <TooltipTrigger asChild>
      <button
        type="button"
        disabled={disabled}
        onClick={(e) => {
          if (disabled) return;
          onClick?.(e);
        }}
        className={cn(
          "transition-all duration-200 outline-none",
          disabled
            ? "cursor-not-allowed text-muted-foreground"
            : "cursor-pointer text-muted-foreground hover:text-primary"
        )}
      >
        {icon}
      </button>
    </TooltipTrigger>
    {/* Explicitly no TooltipArrow component used here to keep it clean */}
    <TooltipContent
      sideOffset={12}
      className="bg-popover border-border text-[11px] font-bold uppercase tracking-wide text-primary px-2 py-1 rounded-md shadow-2xl border [&_svg]:hidden!"
    >
      {disabled ? disabledLabel : label}
    </TooltipContent>
  </Tooltip>
);

const TagPopoverAction = ({ image }: { image: ImagePublic }) => {
  const [open, setOpen] = useState(false);
  const updateTags = useUpdateImageTags();

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <Tooltip delayDuration={0}>
        <TooltipTrigger asChild>
          <PopoverTrigger asChild>
            <button
              type="button"
              onClick={(e) => e.stopPropagation()}
              className="cursor-pointer text-muted-foreground hover:text-primary transition-all duration-200 outline-none"
            >
              <Tag size={18} />
            </button>
          </PopoverTrigger>
        </TooltipTrigger>
        <TooltipContent
          sideOffset={12}
          className="bg-popover border-border text-[11px] font-bold uppercase tracking-wide text-primary px-2 py-1 rounded-md shadow-2xl border [&_svg]:hidden!"
        >
          Tags
        </TooltipContent>
      </Tooltip>
      <PopoverContent
        className="w-64 p-3 bg-popover border-border"
        onClick={(e) => e.stopPropagation()}
      >
        <TagsInput
          value={image.tags}
          onChange={(tags) => updateTags.mutate({ id: image.id, tags })}
          placeholder="Add a tag..."
        />
      </PopoverContent>
    </Popover>
  );
};
