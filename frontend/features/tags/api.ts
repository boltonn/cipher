import { apiClient } from "@/lib/api-client";
import type { Tag, TagTarget, TagTargetType } from "./types";

export const tagService = {
  /** Every user's and model's decision on a target's tags, newest first. */
  list: async (target: TagTarget): Promise<Tag[]> => {
    const { data } = await apiClient.get<Tag[]>("/tags", {
      params: target,
    });
    return data;
  },
  /** Tag names in use on a kind of target, most used first. */
  names: async (targetType: TagTargetType, limit = 200): Promise<string[]> => {
    const { data } = await apiClient.get<string[]>("/tags/names", {
      params: { targetType, limit },
    });
    return data;
  },
  /** Other users whose labels clearing `tag` on these targets would remove. */
  labelAuthors: async (payload: {
    targetType: TagTargetType;
    targetIds: string[];
    tag: string;
  }): Promise<string[]> => {
    const { data } = await apiClient.post<string[]>(
      "/tags/label-authors",
      payload
    );
    return data;
  },
};
