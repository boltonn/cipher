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
import { Calendar, Check, Copy, Maximize2, Search, Tag } from "lucide-react";
import Image from "next/image";
import { useState } from "react";
import { imagesService, useUpdateImageTags } from "../api";
import { ImagePublic, ImageSimilarityResult } from "../types";

interface ImageCardProps {
  image: ImagePublic | ImageSimilarityResult;
  onFindSimilar?: (id: string) => void;
  onExpand?: (image: ImagePublic) => void;
}

export const ImageCard: React.FC<ImageCardProps> = ({
  image,
  onFindSimilar,
  onExpand,
}) => {
  const [copied, setCopied] = useState(false);
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
      <div className="group relative rounded-xl overflow-hidden bg-slate-900/40 border border-white/5 transition-all duration-300 hover:border-indigo-500/40 hover:bg-slate-900/60">
        {/* Flush Image Container */}
        <div
          role="button"
          tabIndex={0}
          className="aspect-4/5 relative w-full bg-background cursor-pointer"
          onClick={() => onExpand?.(image)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              onExpand?.(image);
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

          {/* Action Bar */}
          <div className="absolute inset-x-0 bottom-4 flex justify-center opacity-0 group-hover:opacity-100 translate-y-2 group-hover:translate-y-0 transition-all duration-300 z-10">
            <div
              className="flex items-center gap-4 bg-popover/95 border border-white/10 px-4 py-2 rounded-full shadow-2xl"
              onClick={(e) => e.stopPropagation()} // Prevent card click when clicking bar
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
                    <Check size={18} className="text-indigo-500" />
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
            <span className="absolute top-2 left-2 text-[9px] font-mono font-bold text-indigo-400 bg-indigo-500/10 border border-indigo-500/30 px-1.5 py-0.5 rounded backdrop-blur-sm">
              {(similarityScore * 100).toFixed(0)}% match
            </span>
          )}
        </div>

        {/* Footer */}
        <div className="p-3 border-t border-white/5 space-y-2">
          <div className="flex justify-between items-center h-4">
            {image.dateTaken && (
              <div className="flex items-center gap-1.5 text-slate-500">
                <Calendar size={10} className="text-indigo-500/70" />
                <span className="text-[9px] font-bold uppercase tracking-widest">
                  {new Date(image.dateTaken).toLocaleDateString()}
                </span>
              </div>
            )}
          </div>
          <div className="flex flex-wrap gap-1">
            {visibleTags.map((tag) => (
              <Badge
                key={tag}
                className="bg-indigo-500/10 text-indigo-400 text-[8px] border-none px-1.5 py-0 uppercase font-bold tracking-tight"
              >
                {tag}
              </Badge>
            ))}
            {remainingCount > 0 && (
              <span className="text-[8px] text-slate-600 font-bold ml-1">
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
            ? "cursor-not-allowed text-slate-700"
            : "cursor-pointer text-slate-400 hover:text-indigo-400 hover:drop-shadow-[0_0_8px_rgba(99,102,241,0.8)]"
        )}
      >
        {icon}
      </button>
    </TooltipTrigger>
    {/* Explicitly no TooltipArrow component used here to keep it clean */}
    <TooltipContent
      sideOffset={12}
      className="bg-popover border-white/10 text-[9px] font-bold uppercase tracking-widest text-indigo-400 px-2 py-1 rounded-md shadow-2xl border [&_svg]:hidden!"
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
              className="cursor-pointer text-slate-400 hover:text-indigo-400 transition-all duration-200 hover:drop-shadow-[0_0_8px_rgba(99,102,241,0.8)] outline-none"
            >
              <Tag size={18} />
            </button>
          </PopoverTrigger>
        </TooltipTrigger>
        <TooltipContent
          sideOffset={12}
          className="bg-popover border-white/10 text-[9px] font-bold uppercase tracking-widest text-indigo-400 px-2 py-1 rounded-md shadow-2xl border [&_svg]:hidden!"
        >
          Tags
        </TooltipContent>
      </Tooltip>
      <PopoverContent
        className="w-64 p-3 bg-popover border-white/10"
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
