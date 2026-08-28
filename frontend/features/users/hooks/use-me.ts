import { useQuery } from "@tanstack/react-query";
import { userService } from "../api";

const userKeys = {
  all: ["users"] as const,
  me: () => [...userKeys.all, "me"] as const,
};

export function useMe() {
  return useQuery({
    queryKey: userKeys.me(),
    queryFn: userService.getMe,
    // The user profile doesn't change often, keep it "fresh" for 5 minutes
    staleTime: 5 * 60 * 1000,
  });
}
