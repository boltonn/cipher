import type { EmailBase, EmailConversation } from "@/features/emails/types";
import { apiClient } from "@/lib/api-client";
import { useQuery } from "@tanstack/react-query";

export const emailsService = {
  getByFileId: async (fileId: string): Promise<EmailBase> => {
    const { data } = await apiClient.get<EmailBase>(`/files/${fileId}/email`);
    return data;
  },
  getConversation: async (fileId: string): Promise<EmailConversation> => {
    const { data } = await apiClient.get<EmailConversation>(
      `/files/${fileId}/conversation`
    );
    return data;
  },
};

export function useEmail(fileId: string | undefined) {
  return useQuery({
    queryKey: ["emails", fileId],
    queryFn: () => emailsService.getByFileId(fileId as string),
    enabled: !!fileId,
    staleTime: 60_000,
  });
}

export function useEmailConversation(fileId: string | undefined) {
  return useQuery({
    queryKey: ["emails", fileId, "conversation"],
    queryFn: () => emailsService.getConversation(fileId as string),
    enabled: !!fileId,
    staleTime: 60_000,
  });
}
