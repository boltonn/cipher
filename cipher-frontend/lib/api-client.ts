import axios from "axios";
import { toast } from "sonner";

export const baseURL =
  typeof window === "undefined"
    ? process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api"
    : process.env.NEXT_PUBLIC_API_URL || "/api";

export const apiClient = axios.create({
  baseURL,
  headers: {
    "Content-Type": "application/json",
  },
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const message =
      error.response?.data?.detail ??
      error.response?.data?.message ??
      error.message;
    toast.error(message);
    return Promise.reject(error);
  }
);
