"use client";
import { commentsService } from "@/features/comments/api";
import { CommentableType } from "@/features/comments/types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

export function useComments(commentableType: CommentableType, commentableId: string) {
  return useQuery({
    queryKey: ["comments", commentableType, commentableId],
    queryFn: () => commentsService.list(commentableType, commentableId),
  });
}

export function useAddComment(commentableType: CommentableType, commentableId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (content: string) => commentsService.create({ content, commentableType, commentableId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["comments", commentableType, commentableId] });
    },
  });
}

export function useUpdateComment(commentableType: CommentableType, commentableId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, content }: { id: string; content: string }) => commentsService.update(id, { content }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["comments", commentableType, commentableId] });
    },
  });
}

export function useDeleteComment(commentableType: CommentableType, commentableId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => commentsService.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["comments", commentableType, commentableId] });
    },
  });
}
