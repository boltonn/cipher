"use client";

import {
  ChevronLeft,
  ChevronRight,
  Database,
  FileText,
  HardDrive,
  Loader2,
  MessageSquare,
  ShieldCheck,
} from "lucide-react";
import Image from "next/image";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import type { File, FileMetadata } from "@/features/files/types";
import { cn } from "@/lib/utils";
import { imagesService } from "../api";
import { MOCK_FILES, MOCK_INSTANCES } from "../constants";
import { ImagePublic } from "../types";

interface ImageDetailDialogProps {
  image: ImagePublic;
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  onNext: () => void;
  onPrev: () => void;
  hasMore: boolean;
  hasPrev: boolean;
}

export function ImageDetailDialog({
  image,
  isOpen,
  onOpenChange,
  onNext,
  onPrev,
  hasMore,
  hasPrev,
}: ImageDetailDialogProps) {
  const [fileInfo, setFileInfo] = useState<FileMetadata | null>(null);
  const [instances, setInstances] = useState<File[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const cancelledRef = useRef(false);

  console.log(fileInfo, instances);

  const handleOpenChange = (open: boolean) => {
    if (open) {
      cancelledRef.current = false;
      setIsLoading(true);
      const run = async () => {
        if (cancelledRef.current) return;
        const cancelled = await new Promise<boolean>((r) =>
          setTimeout(() => r(cancelledRef.current), 600)
        );
        if (cancelled) return;
        setFileInfo(MOCK_FILES[0]);
        setInstances(MOCK_INSTANCES[0]);
        setIsLoading(false);
      };
      run();
    } else {
      cancelledRef.current = true;
    }
    onOpenChange(open);
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleOpenChange}>
      <DialogContent
        className="max-w-[95vw] md:max-w-[90vw] lg:max-w-[85vw] w-full h-[92vh] 
        p-0 bg-[#0f1115] border-white/10 overflow-hidden flex flex-col md:flex-row shadow-2xl 
        ring-1 ring-white/5 gap-0"
        aria-describedby={undefined}
      >
        {/* Left: Image Preview Section */}
        <div className="flex-1 bg-black relative flex items-center justify-center p-8 group/image">
          <Image
            src={imagesService.getImageUrl(image.id)}
            alt={image.id}
            fill
            className="object-contain transition-opacity duration-300"
            unoptimized
            sizes="(max-width: 768px) 100vw, (max-width: 1200px) 50vw, 33vw"
          />

          <div className="absolute inset-0 flex items-center justify-between px-4 pointer-events-none">
            <Button
              variant="ghost"
              size="icon"
              onClick={onPrev}
              disabled={!hasPrev}
              className={cn(
                "h-14 w-14 rounded-full bg-black/40 border border-white/10 text-white pointer-events-auto opacity-0 group-hover/image:opacity-100 transition-all disabled:opacity-0",
                "hover:bg-indigo-500/20 hover:text-indigo-400 hover:border-indigo-500/50"
              )}
            >
              <ChevronLeft className="h-8 w-8" strokeWidth={1.5} />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={onNext}
              disabled={!hasMore}
              className={cn(
                "h-14 w-14 rounded-full bg-black/40 border border-white/10 text-white pointer-events-auto opacity-0 group-hover/image:opacity-100 transition-all disabled:opacity-0",
                "hover:bg-indigo-500/20 hover:text-indigo-400 hover:border-indigo-500/50"
              )}
            >
              <ChevronRight className="h-8 w-8" strokeWidth={1.5} />
            </Button>
          </div>
        </div>

        {/* Right: Data Sidebar */}
        <aside className="w-full md:w-100 border-l border-white/5 flex flex-col bg-[#161920] relative">
          {/* Loading Overlay for Sidebar */}
          {isLoading && (
            <div className="absolute inset-0 z-50 bg-[#161920]/80 backdrop-blur-sm flex flex-col items-center justify-center space-y-4">
              <Loader2 className="h-8 w-8 animate-spin text-indigo-500" />
              <span className="text-[10px] font-black uppercase tracking-[0.3em] text-indigo-400/70">
                Parsing Metadata...
              </span>
            </div>
          )}

          <DialogHeader className="p-12 pb-4">
            <div className="flex items-center justify-between mb-1">
              <DialogTitle className="text-white tracking-[0.2em] uppercase text-[10px] font-black">
                Image Details
              </DialogTitle>
              <span className="text-[10px] font-mono text-indigo-400 bg-indigo-500/10 px-2 py-0.5 rounded border border-indigo-500/20">
                {image.width} × {image.height}
              </span>
            </div>
            <p className="text-[10px] text-slate-500 font-mono truncate">
              UID: {image.id}
            </p>
          </DialogHeader>

          <Separator className="bg-white/5" />

          <ScrollArea className="flex-1">
            <div className="p-4">
              {/* File Section */}
              {fileInfo && (
                <section className="p-4 rounded-xl bg-black/40 border border-white/5 space-y-4">
                  <div className="flex items-center gap-2">
                    <FileText size={14} className="text-emerald-500" />
                    <h4 className="text-[10px] font-black text-slate-300 uppercase tracking-widest">
                      File Metadata
                    </h4>
                  </div>
                  <div className="space-y-3">
                    <div className="space-y-1">
                      <p className="text-[8px] text-slate-500 font-bold uppercase">
                        SHA256 Hash
                      </p>
                      <p className="text-[9px] font-mono text-emerald-500/80 break-all bg-emerald-500/5 p-1.5 rounded border border-emerald-500/10 uppercase">
                        {fileInfo.sha256}
                      </p>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <DataPoint label="Mime Type" value={fileInfo.mimeType} />
                      <DataPoint
                        label="Storage"
                        value={`${(fileInfo.size / (1024 * 1024)).toFixed(2)} MB`}
                      />
                    </div>
                  </div>
                </section>
              )}

              <Separator className="my-2 bg-white/5" />

              {/* EXIF Section */}
              <section className="p-4 rounded-xl bg-black/40 border border-white/5 space-y-4">
                <div className="flex items-center gap-2 mb-4">
                  <ShieldCheck size={14} className="text-indigo-500" />
                  <h4 className="text-[10px] font-black text-slate-300 uppercase tracking-widest">
                    Telemetry
                  </h4>
                </div>
                <div className="grid grid-cols-2 gap-y-6 gap-x-4">
                  <DataPoint
                    label="Equipment"
                    value={`${image.cameraMake || "—"} ${image.cameraModel || ""}`}
                  />
                  <DataPoint
                    label="Aperture"
                    value={image.aperture ? `ƒ/${image.aperture}` : "—"}
                  />
                  <DataPoint label="ISO" value={image.iso?.toString() || "—"} />
                  <DataPoint
                    label="Focal"
                    value={image.focalLength ? `${image.focalLength}mm` : "—"}
                  />
                  <DataPoint
                    label="Timestamp"
                    value={
                      image.dateTaken
                        ? new Date(image.dateTaken).toLocaleDateString()
                        : "—"
                    }
                  />
                  <DataPoint
                    label="Elevation"
                    value={
                      image.gpsAltitude
                        ? `${image.gpsAltitude.toFixed(1)}m`
                        : "—"
                    }
                  />
                </div>
              </section>

              {/* Interaction Area */}
              <Tabs defaultValue="instances" className="w-full mt-6">
                <TabsList className="w-full bg-slate-950/50 border border-white/5 h-10 p-1">
                  <TabsTrigger
                    value="instances"
                    className="flex-1 text-[10px] uppercase font-bold tracking-widest data-[state=active]:bg-indigo-600"
                  >
                    <HardDrive size={12} className="mr-2" /> Instances
                  </TabsTrigger>
                  <TabsTrigger
                    value="comments"
                    className="flex-1 text-[10px] uppercase font-bold tracking-widest data-[state=active]:bg-indigo-600"
                  >
                    <MessageSquare size={12} className="mr-2" /> Comments
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="instances" className="space-y-3">
                  {instances.length > 0 ? (
                    instances.map((inst) => (
                      <div
                        key={inst.id}
                        className="p-3 rounded-lg bg-white/2 border border-white/5 hover:border-indigo-500/30 transition-colors group"
                      >
                        <div className="flex items-center gap-2 mb-1">
                          <Database size={10} className="text-indigo-400" />
                          <span className="text-[10px] font-bold text-slate-300 truncate w-full group-hover:text-indigo-300">
                            {inst.filename}
                          </span>
                        </div>
                        <p className="text-[9px] font-mono text-slate-500 break-all leading-relaxed px-1 border-l border-white/5 ml-1">
                          {inst.path}
                        </p>
                        <div className="mt-2 flex items-center justify-between pt-2 border-t border-white/5">
                          <span className="text-[8px] uppercase font-bold text-slate-600 tracking-tighter">
                            {inst.device || "PRIMARY_NODE"}
                          </span>
                          <span className="text-[8px] font-mono text-slate-600 uppercase">
                            {inst.dateCreated
                              ? new Date(inst.dateCreated).toLocaleDateString()
                              : "UNTITLED"}
                          </span>
                        </div>
                      </div>
                    ))
                  ) : (
                    <p className="text-[10px] text-slate-600 text-center italic py-4">
                      No file instances mapped.
                    </p>
                  )}
                </TabsContent>

                <TabsContent value="comments" className="mt-6">
                  <div className="p-4 bg-indigo-500/5 rounded-lg border border-indigo-500/10">
                    <p className="text-xs text-slate-300 leading-relaxed italic">
                      System-generated: Neural similarity match confirmed.
                      Tagged as high-priority asset.
                    </p>
                    <span className="text-[9px] text-indigo-500/60 font-black uppercase tracking-widest mt-3 block">
                      Analyst System // AUTO_GEN
                    </span>
                  </div>
                </TabsContent>
              </Tabs>
            </div>
          </ScrollArea>

          <div className="p-4 bg-slate-950/50 border-t border-white/5">
            <input
              aria-label="Comment"
              placeholder="Make a comment..."
              className="w-full bg-[#0f1115] border border-white/10 rounded-md p-2.5 text-xs text-white focus:outline-none focus:border-indigo-500 transition-all placeholder:text-slate-700"
            />
          </div>
        </aside>
      </DialogContent>
    </Dialog>
  );
}

const DataPoint = ({ label, value }: { label: string; value: string }) => (
  <div className="flex flex-col gap-0.5">
    <p className="text-slate-600 uppercase text-[8px] font-black tracking-widest leading-none mb-1">
      {label}
    </p>
    <p className="text-slate-200 font-mono text-[11px] truncate leading-none">
      {value}
    </p>
  </div>
);
