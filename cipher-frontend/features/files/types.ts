export interface FileMetadata {
  filetype: string;
  filetypeGroup: string;
  filetypeName?: string;
  md5: string;
  mimeType: string;
  sha256: string;
  size: number;
}

export interface FileInstance {
  id: string;
  datasetId: string;
  dateCreated?: string;
  dateLastUpdated?: string;
  filename: string;
  path?: string;
  uri: string;
}

export interface File extends FileInstance, FileMetadata {}
