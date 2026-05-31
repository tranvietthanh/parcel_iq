"use server";

import { adminAction } from "@/lib/admin-action";

export type TaskDetail = {
  id: string;
  state: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled" | "retrying";
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
};

type TaskListResponse = {
  items: TaskDetail[];
  total: number;
};

/**
 * Get list of active/recent Celery tasks.
 */
export async function getTasks(): Promise<TaskDetail[]> {
  const response = await adminAction<TaskListResponse>("GET", "/tasks");
  return response.items || [];
}

/**
 * Get details for a specific task.
 */
export async function getTaskDetail(taskId: string): Promise<TaskDetail> {
  return adminAction<TaskDetail>("GET", `/tasks/${taskId}`);
}

/**
 * Cancel a running or queued task.
 */
export async function cancelTask(taskId: string): Promise<{ action: string }> {
  return adminAction("POST", `/tasks/${taskId}/cancel`);
}

/**
 * Retry a failed task.
 */
export async function retryTask(taskId: string): Promise<{ action: string }> {
  return adminAction("POST", `/tasks/${taskId}/retry`);
}
