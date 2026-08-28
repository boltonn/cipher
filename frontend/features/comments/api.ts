import {
  Comment,
  CommentableType,
  CommentCreate,
  CommentPublic,
  CommentUpdate,
} from "@/features/comments/types";
import { apiClient } from "@/lib/api-client";

const commentsBaseURL = "/comments";

export const commentsService = {
  list: (commentableType: CommentableType, commentableId: string) =>
    apiClient
      .get<CommentPublic[]>(commentsBaseURL, { params: { commentableType, commentableId } })
      .then((res) => res.data),

  create: (payload: CommentCreate) =>
    apiClient.post<Comment>(commentsBaseURL, payload).then((res) => res.data),

  update: (id: string, payload: CommentUpdate) =>
    apiClient.patch<Comment>(`${commentsBaseURL}/${id}`, payload).then((res) => res.data),

  delete: (id: string) =>
    apiClient.delete<boolean>(`${commentsBaseURL}/${id}`).then((res) => res.data),
};
