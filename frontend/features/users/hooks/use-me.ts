import { useQuery } from "@tanstack/react-query";
import { userService } from "../api";
import { userKeys } from "./use-users";

export function useMe() {
  return useQuery({
    queryKey: userKeys.me(),
    queryFn: userService.getMe,
    // The user profile doesn't change often, keep it "fresh" for 5 minutes
    staleTime: 5 * 60 * 1000,
  });
}

/** Whether the signed-in user is an admin (false while loading). */
export function useIsAdmin() {
  return useMe().data?.isAdmin ?? false;
}
