import { apiClient } from "@/lib/api-client";
import type { PaginatedResponse } from "@/types/common";
import type {
  User,
  UserCreate,
  UserDatasetsUpdate,
  UsersRequest,
  UserUpdate,
} from "./types";

export const userService = {
  /** The signed-in user (the seeded Dev Admin in development). */
  getMe: async (): Promise<User> => {
    const { data } = await apiClient.get<User>("/users/me");
    return data;
  },

  // --- admin only (/admin) ---
  list: async (
    request: UsersRequest,
    page: number
  ): Promise<PaginatedResponse<User>> => {
    const { data } = await apiClient.get<PaginatedResponse<User>>(
      "/admin/users",
      {
        params: { ...request, page },
      }
    );
    return data;
  },
  create: async (payload: UserCreate): Promise<User> => {
    const { data } = await apiClient.post<User>("/admin/users", payload);
    return data;
  },
  update: async (id: string, payload: UserUpdate): Promise<User> => {
    const { data } = await apiClient.patch<User>(`/admin/users/${id}`, payload);
    return data;
  },
  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/admin/users/${id}`);
  },
  getDatasetIds: async (id: string): Promise<string[]> => {
    const { data } = await apiClient.get<string[]>(
      `/admin/users/${id}/datasets`
    );
    return data;
  },
  setDatasetIds: async (
    id: string,
    payload: UserDatasetsUpdate
  ): Promise<string[]> => {
    const { data } = await apiClient.put<string[]>(
      `/admin/users/${id}/datasets`,
      payload
    );
    return data;
  },
};
