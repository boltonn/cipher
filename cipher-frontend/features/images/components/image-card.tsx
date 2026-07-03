"use client";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Calendar, Check, Copy, Maximize2, Search, Tag } from "lucide-react";
import Image from "next/image";
import { useState } from "react";
import { imagesService } from "../api";
import { ImagePublic } from "../types";

interface ImageCardProps {
  image: ImagePublic;
  onFindSimilar?: (id: string) => void;
  onTag?: (id: string, tag: string) => void;
  onExpand?: (image: ImagePublic) => void;
}

export const ImageCard: React.FC<ImageCardProps> = ({
  image,
  onFindSimilar,
  onTag,
  onExpand,
}) => {
  const [copied, setCopied] = useState(false);
  const imageUrl = imagesService.getImageUrl(image.id);
  const visibleTags = image.tags.slice(0, 3);
  const remainingCount = image.tags.length - visibleTags.length;

  const handleCopyId = (e?: React.MouseEvent<HTMLButtonElement>) => {
    e?.stopPropagation();
    navigator.clipboard.writeText(image.id);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <TooltipProvider>
      <Card className="group relative rounded-xl overflow-hidden bg-[#0a0c10] border-white/5 transition-all duration-300 hover:border-indigo-500/40">
        {/* Flush Image Container */}
        <button
          type="button"
          className="aspect-4/5 relative w-full bg-slate-950 cursor-pointer"
          onClick={() => onExpand?.(image)}
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
              className="flex items-center gap-4 bg-[#161920]/95 border border-white/10 px-4 py-2 rounded-full shadow-2xl"
              onClick={(e) => e.stopPropagation()} // Prevent card click when clicking bar
            >
              <NavAction
                icon={<Search size={18} />}
                label="Find Similar"
                onClick={() => onFindSimilar?.(image.id)}
              />
              <NavAction
                icon={<Tag size={18} />}
                label="Add Tag"
                onClick={() => onTag?.(image.id, "new-tag")}
              />
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
        </button>

        {/* Footer */}
        <div className="p-3 bg-[#0f1115] border-t border-white/5 space-y-2">
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
      </Card>
    </TooltipProvider>
  );
};

const NavAction = ({
  icon,
  label,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  onClick?: (e?: React.MouseEvent<HTMLButtonElement>) => void;
}) => (
  <Tooltip delayDuration={0}>
    <TooltipTrigger asChild>
      <button
        type="button"
        onClick={(e) => onClick?.(e)}
        className="cursor-pointer text-slate-400 hover:text-indigo-400 transition-all duration-200 hover:drop-shadow-[0_0_8px_rgba(99,102,241,0.8)] outline-none"
      >
        {icon}
      </button>
    </TooltipTrigger>
    {/* Explicitly no TooltipArrow component used here to keep it clean */}
    <TooltipContent
      sideOffset={12}
      className="bg-[#161920] border-white/10 text-[9px] font-bold uppercase tracking-widest text-indigo-400 px-2 py-1 rounded-md shadow-2xl border [&_svg]:hidden!"
    >
      {label}
    </TooltipContent>
  </Tooltip>
);
