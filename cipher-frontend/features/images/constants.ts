import { Dataset } from "../datasets/types";

export const DATASETS: Dataset[] = [
  {
    id: "adf5c3e2-1c4b-4e2b-9f3e-2b1c4b5e6f7a",
    name: "Nature Photos",
    description: "A collection of beautiful nature photographs.",
    dateCreated: "2023-01-15T10:00:00Z",
    dateLastUpdated: "2023-06-20T12:30:00Z",
  },
  {
    id: "b2e6f7a8-3c4d-5e6f-7a8b-9c0d1e2f3a4b",
    name: "Cityscapes",
    description: "Images capturing urban environments and city life.",
    dateCreated: "2022-11-05T14:20:00Z",
    dateLastUpdated: "2023-05-18T09:15:00Z",
  },
  {
    id: "c3d4e5f6-7a8b-9c0d-1e2f-3a4b5c6d7e8f",
    name: "Wildlife",
    description: "Photos of animals in their natural habitats.",
    dateCreated: "2023-03-22T08:45:00Z",
    dateLastUpdated: "2023-07-10T11:50:00Z",
  },
];

import { FileInstance, FileMetadata } from "@/features/files/types";

/**
 * Mock File Data
 * Keyed by fileId to simulate a database lookup.
 * This represents the immutable properties of the file itself.
 */
export const MOCK_FILES: FileMetadata[] = [
  {
    filetype: "png",
    filetypeGroup: "image",
    md5: "e99a18c428cb38d5f260853678922e03",
    sha256: "88321a5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3",
    size: 15728640, // 15MB
    mimeType: "image/png",
  },
  {
    filetype: "jpg",
    filetypeGroup: "image",
    md5: "d41d8cd98f00b204e9800998ecf8427e",
    sha256: "99432b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3",
    size: 8388608, // 8MB
    mimeType: "image/jpeg",
  },
];

/**
 * Mock File Instance Data
 * Represents where the files physically live on disk or cloud.
 * Keyed by fileId, containing an array of instances.
 */
export const MOCK_INSTANCES: FileInstance[][] = [
  [
    {
      id: "inst_01",
      datasetId: "ds_vector_prime",
      dateCreated: "2024-10-12T14:35:00Z",
      dateLastUpdated: "2024-10-12T14:35:00Z",
      filename: "terminal_corridor_v1.png",
      path: "/data/renders/2024/project_neon/terminal_corridor_v1.png",
      uri: "file://storage-01/renders/terminal_corridor_v1.png",
    },
    {
      id: "inst_02",
      datasetId: "ds_archive_global",
      dateCreated: "2024-10-13T02:00:00Z",
      dateLastUpdated: "2024-10-13T02:00:00Z",
      filename: "backup_corridor_v1.png",
      path: "/backups/images/terminal_corridor_v1.png",
      uri: "s3://backups/terminal_corridor_v1.png",
    },
  ],
  [
    {
      id: "inst_03",
      datasetId: "ds_photography_pro",
      dateCreated: "2024-11-05T09:20:00Z",
      dateLastUpdated: "2024-11-05T10:00:00Z",
      filename: "portrait_study_04.jpg",
      path: "/work/photography/portraits/portrait_study_04.jpg",
      uri: "file://C:/Users/Admin/Photos/portrait_study_04.jpg",
    },
  ],
];
export const FILE_TYPES = [
  "jpeg",
  "png",
  "webp",
  "heic",
  "tiff",
  "bmp",
  "gif",
  "svg",
];
export const AVAILABLE_TAGS = [
  "Nature",
  "City",
  "Technology",
  "Person",
  "Animal",
  "Abstract",
  "Minimalist",
  "Vibrant",
];
