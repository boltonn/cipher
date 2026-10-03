export interface User {
  id: string;
  name: string;
  email: string;
  /** Admins see every dataset and manage users and dataset access. */
  isAdmin: boolean;
  dateCreated: string;
  dateUpdated: string;
}

export interface UsersRequest {
  query?: string;
  limit?: number;
}

export interface UserCreate {
  name: string;
  email: string;
  isAdmin?: boolean;
}

export type UserUpdate = Partial<UserCreate>;

/** The complete set of datasets a user is a member of -- replaces what they had. */
export interface UserDatasetsUpdate {
  datasetIds: string[];
}
