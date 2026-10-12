import type {
  FieldTypeOption,
  RelationshipVerbOption,
  TableMapping,
  TableMappingDetail,
  TableView,
} from "@/features/tables/types";
import { apiClient } from "@/lib/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

const tablesBaseURL = "/tables";

export const tablesService = {
  table: (sha256: string, datasetId?: string): Promise<TableView> =>
    apiClient.get<TableView>(`${tablesBaseURL}/${sha256}`, { params: { datasetId } }).then((res) => res.data),

  updateMapping: (id: string, mapping: TableMapping): Promise<TableMappingDetail> =>
    apiClient
      .put<TableMappingDetail>(`${tablesBaseURL}/mappings/${id}`, { mapping })
      .then((res) => res.data),

  verifyMapping: (id: string): Promise<TableMappingDetail> =>
    apiClient.post<TableMappingDetail>(`${tablesBaseURL}/mappings/${id}/verify`).then((res) => res.data),

  fieldTypes: (): Promise<FieldTypeOption[]> =>
    apiClient.get<FieldTypeOption[]>(`${tablesBaseURL}/field-types`).then((res) => res.data),

  verbs: (): Promise<RelationshipVerbOption[]> =>
    apiClient.get<RelationshipVerbOption[]>(`${tablesBaseURL}/verbs`).then((res) => res.data),
};

const tableKey = (sha256: string) => ["table", sha256] as const;

/** A table by content hash with each sheet's mapping; `mappings` is empty before `cipher map-tables`. */
export function useTable(sha256: string, datasetId?: string) {
  return useQuery({ queryKey: tableKey(sha256), queryFn: () => tablesService.table(sha256, datasetId) });
}

export function useFieldTypes() {
  return useQuery({ queryKey: ["table-field-types"], queryFn: tablesService.fieldTypes, staleTime: Infinity });
}

export function useRelationshipVerbs() {
  return useQuery({ queryKey: ["table-verbs"], queryFn: tablesService.verbs, staleTime: Infinity });
}

function replaceIn(table: TableView | undefined, detail: TableMappingDetail): TableView | undefined {
  return table && { ...table, mappings: table.mappings.map((m) => (m.id === detail.id ? detail : m)) };
}

/** Save an edit; the server re-checks everything you didn't set and returns the new mapping. */
export function useUpdateTableMapping(sha256: string, mappingId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (mapping: TableMapping) => tablesService.updateMapping(mappingId, mapping),
    onSuccess: (detail) => qc.setQueryData(tableKey(sha256), (old: TableView | undefined) => replaceIn(old, detail)),
    onError: () => toast.error("Couldn't save the change"),
  });
}

export function useVerifyTableMapping(sha256: string, mappingId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => tablesService.verifyMapping(mappingId),
    onSuccess: (detail) => {
      qc.setQueryData(tableKey(sha256), (old: TableView | undefined) => replaceIn(old, detail));
      const n = detail.files.length;
      toast.success(`Mapping verified — ${n} ${n === 1 ? "file" : "files"} queued for emit-tables`);
    },
    onError: () => toast.error("Couldn't verify the mapping"),
  });
}
