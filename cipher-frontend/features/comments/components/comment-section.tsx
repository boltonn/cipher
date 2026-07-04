"use client";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  useAddComment,
  useComments,
  useDeleteComment,
  useUpdateComment,
} from "@/features/comments/hooks/use-comments";
import { CommentableType } from "@/features/comments/types";
import { formatDistanceToNow } from "date-fns";
import { Check, Loader2, MessageSquare, Pencil, Trash2, X } from "lucide-react";
import { useState } from "react";

interface CommentSectionProps {
  commentableType: CommentableType;
  commentableId: string;
}

function initials(name: string) {
  return name
    .split(" ")
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

export function CommentSection({ commentableType, commentableId }: CommentSectionProps) {
  const { data: comments, isPending } = useComments(commentableType, commentableId);
  const addComment = useAddComment(commentableType, commentableId);
  const updateComment = useUpdateComment(commentableType, commentableId);
  const deleteComment = useDeleteComment(commentableType, commentableId);

  const [draft, setDraft] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState("");

  const handleAdd = () => {
    if (!draft.trim()) return;
    addComment.mutate(draft.trim(), { onSuccess: () => setDraft("") });
  };

  const startEdit = (id: string, content: string) => {
    setEditingId(id);
    setEditDraft(content);
  };

  const commitEdit = () => {
    if (!editingId || !editDraft.trim()) return;
    updateComment.mutate(
      { id: editingId, content: editDraft.trim() },
      { onSuccess: () => setEditingId(null) }
    );
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <MessageSquare size={14} className="text-indigo-500" />
        <h4 className="text-[10px] font-black text-slate-300 uppercase tracking-widest">
          Comments {comments?.length ? `(${comments.length})` : ""}
        </h4>
      </div>

      <div className="flex flex-col gap-3">
        {isPending ? (
          <Loader2 size={16} className="animate-spin text-slate-600" />
        ) : comments?.length ? (
          comments.map((comment) => (
            <div key={comment.id} className="flex gap-3 group">
              <div className="h-9 w-9 shrink-0 rounded-full bg-indigo-500/20 text-indigo-300 text-xs font-bold flex items-center justify-center">
                {initials(comment.userName)}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-slate-200">{comment.userName}</span>
                  <span className="text-[11px] text-slate-500 font-mono">
                    {formatDistanceToNow(new Date(comment.dateCreated), { addSuffix: true })}
                  </span>
                </div>
                {editingId === comment.id ? (
                  <div className="mt-1.5 space-y-2">
                    <Textarea
                      value={editDraft}
                      onChange={(e) => setEditDraft(e.target.value)}
                      className="bg-slate-900/40 border-white/10 text-sm min-h-20"
                    />
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        onClick={commitEdit}
                        disabled={updateComment.isPending}
                        className="h-8 gap-1 text-xs bg-indigo-600 hover:bg-indigo-500"
                      >
                        <Check size={13} /> Save
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setEditingId(null)}
                        className="h-8 gap-1 text-xs text-slate-400"
                      >
                        <X size={13} /> Cancel
                      </Button>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-slate-300 leading-relaxed mt-1 break-words">
                    {comment.content}
                  </p>
                )}
              </div>
              {editingId !== comment.id && (
                <div className="flex items-start gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    type="button"
                    onClick={() => startEdit(comment.id, comment.content)}
                    className="text-slate-600 hover:text-indigo-400 p-1.5"
                    aria-label="Edit comment"
                  >
                    <Pencil size={14} />
                  </button>
                  <button
                    type="button"
                    onClick={() => deleteComment.mutate(comment.id)}
                    className="text-slate-600 hover:text-rose-400 p-1.5"
                    aria-label="Delete comment"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              )}
            </div>
          ))
        ) : (
          <p className="text-[11px] text-slate-600 italic">No comments yet.</p>
        )}
      </div>

      <div className="flex flex-col gap-2 pt-2 border-t border-white/5">
        <Textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Add a comment..."
          className="bg-slate-900/40 border-white/10 text-sm min-h-24"
        />
        <Button
          onClick={handleAdd}
          disabled={!draft.trim() || addComment.isPending}
          className="self-end h-9 gap-2 text-xs font-bold uppercase tracking-widest bg-indigo-600 hover:bg-indigo-500"
        >
          {addComment.isPending && <Loader2 size={14} className="animate-spin" />}
          Comment
        </Button>
      </div>
    </div>
  );
}
