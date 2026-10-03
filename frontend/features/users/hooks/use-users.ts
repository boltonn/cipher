import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { userService } from "../api";
import type { UserCreate, UsersRequest, UserUpdate } from "../types";

export const userKeys = {
  all: ["users"] as const,
  me: () => [...userKeys.all, "me"] as const,
  list: (request: UsersRequest) => [...userKeys.all, "list", request] as const,
  datasets: (id: string) => [...userKeys.all, id, "datasets"] as const,
};

/** Admin: users matching a name/email query, infinitely scrolled. */
export function useUsers(request: UsersRequest) {
  return useInfiniteQuery({
    queryKey: userKeys.list({ ...request }),
    queryFn: ({ pageParam = 1 }) => userService.list(request, pageParam),
    initialPageParam: 1,
    getNextPageParam: (lastPage) =>
      lastPage.hasMore ? lastPage.page + 1 : undefined,
  });
}

/** Admin: the datasets a user is a member of. */
export function useUserDatasetIds(id: string | undefined) {
  return useQuery({
    queryKey: userKeys.datasets(id ?? ""),
    queryFn: () => userService.getDatasetIds(id as string),
    enabled: !!id,
  });
}

export function useSetUserDatasets(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (datasetIds: string[]) =>
      userService.setDatasetIds(id, { datasetIds }),
    onSuccess: (datasetIds) => {
      queryClient.setQueryData(userKeys.datasets(id), datasetIds);
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
    },
  });
}

export function useCreateUser(onSuccess?: () => void) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: UserCreate) => userService.create(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: userKeys.all });
      onSuccess?.();
    },
  });
}

export function useUpdateUser(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: UserUpdate) => userService.update(id, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: userKeys.all }),
  });
}

export function useDeleteUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => userService.delete(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: userKeys.all }),
  });
}
