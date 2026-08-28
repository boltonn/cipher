export type CommentableType = "dataset" | "image" | "person" | "file" | "entity";

export interface Comment {
  id: string;
  content: string;
  commentableType: CommentableType;
  commentableId: string;
  userId: string;
  dateCreated: string;
  dateUpdated: string;
}

export interface CommentPublic extends Comment {
  userName: string;
}

export interface CommentCreate {
  content: string;
  commentableType: CommentableType;
  commentableId: string;
}

export interface CommentUpdate {
  content?: string;
}
