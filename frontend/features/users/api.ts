import { apiClient } from "@/lib/api-client";
import { User } from "./types";

export const userService = {
  // Get the currently authenticated user
  getMe: async (): Promise<User> => {
    const { data } = await apiClient.get<User>("/users/me");
    return data;
  },

  // Get a specific user by ID if needed later
  getUser: async (id: string): Promise<User> => {
    const { data } = await apiClient.get<User>(`/users/${id}`);
    return data;
  },
};
