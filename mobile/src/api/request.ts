import type {
  CoinTransaction,
  DocumentItem,
  FocusStats,
  OnboardingPayload,
  OnboardingResponse,
  Pet,
  PlanGenerateRequest,
  PlanItem,
  Question,
  QuestionGeneratePayload,
  StudyPlan,
  WrongBookItem,
} from "@/types";

const BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ||
  "http://localhost:8000/api/v1";

function getToken(): string {
  return (uni.getStorageSync("ai_study_token") as string) || "";
}

export function setToken(token: string): void {
  uni.setStorageSync("ai_study_token", token);
}

export function clearToken(): void {
  uni.removeStorageSync("ai_study_token");
  uni.removeStorageSync("ai_study_user");
}

export function request<T>(options: {
  url: string;
  method?: "GET" | "POST" | "PUT";
  data?: unknown;
}): Promise<T> {
  return new Promise((resolve, reject) => {
    uni.request({
      url: `${BASE_URL}${options.url}`,
      method: options.method || "GET",
      data: options.data as Record<string, unknown>,
      header: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${getToken()}`,
      },
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data as T);
        } else if (res.statusCode === 401) {
          clearToken();
          reject(res.data);
        } else {
          reject(res.data);
        }
      },
      fail: reject,
    });
  });
}

export function uploadDocument(filePath: string): Promise<DocumentItem> {
  return new Promise((resolve, reject) => {
    uni.uploadFile({
      url: `${BASE_URL}/files/upload`,
      filePath,
      name: "file",
      header: { Authorization: `Bearer ${getToken()}` },
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(JSON.parse(res.data) as DocumentItem);
        } else {
          reject(res.data);
        }
      },
      fail: reject,
    });
  });
}

export const api = {
  login: (account: string, password: string) =>
    request<{ access_token: string; user: { username: string } }>({
      url: "/auth/login",
      method: "POST",
      data: { account, password },
    }),
  register: (payload: { email: string; username: string; password: string }) =>
    request<{ access_token: string; user: { username: string } }>({
      url: "/auth/register",
      method: "POST",
      data: payload,
    }),
  stats: () => request<FocusStats>({ url: "/focus/stats" }),
  plans: () => request<StudyPlan[]>({ url: "/plans" }),
  generatePlan: (data: PlanGenerateRequest) =>
    request<StudyPlan>({ url: "/plans/generate", method: "POST", data }),
  completePlanItem: (itemId: number, completed: boolean) =>
    request<PlanItem>({
      url: `/plans/items/${itemId}`,
      method: "PUT",
      data: { completed },
    }),
  questions: () => request<Question[]>({ url: "/questions" }),
  generateQuestions: (data: QuestionGeneratePayload) =>
    request<Question[]>({ url: "/questions/generate", method: "POST", data }),
  submitAnswer: (questionId: number, userAnswer: string) =>
    request<{ is_correct: boolean }>({
      url: `/questions/${questionId}/answers`,
      method: "POST",
      data: { user_answer: userAnswer },
    }),
  wrongBook: () => request<WrongBookItem[]>({ url: "/wrong-book" }),
  markMastered: (itemId: number, mastered: boolean) =>
    request<WrongBookItem>({
      url: `/wrong-book/${itemId}`,
      method: "PUT",
      data: { mastered },
    }),
  documents: () => request<DocumentItem[]>({ url: "/files" }),
  parseDocument: (id: number) =>
    request<{ document_id: number; chunks: number }>({
      url: `/files/${id}/parse`,
      method: "POST",
    }),
  fileQuestions: (id: number, data: { count: number; question_type: string }) =>
    request<Question[]>({ url: `/files/${id}/questions`, method: "POST", data }),
  startFocus: (taskLabel: string, durationMinutes: number) =>
    request<{ id: number }>({
      url: "/focus/sessions",
      method: "POST",
      data: { task_label: taskLabel, duration_minutes: durationMinutes },
    }),
  completeFocus: (id: number) =>
    request<{ id: number }>({
      url: `/focus/sessions/${id}/complete`,
      method: "PUT",
    }),
  pet: () => request<Pet>({ url: "/pets" }),
  feedPet: (id: number, amount: number) =>
    request<Pet>({ url: `/pets/${id}/feed`, method: "POST", data: { amount } }),
  transactions: () => request<CoinTransaction[]>({ url: "/coins/transactions" }),
  getOnboarding: () =>
    request<OnboardingResponse>({ url: "/users/me/onboarding" }),
  submitOnboarding: (data: OnboardingPayload) =>
    request<OnboardingResponse>({
      url: "/onboarding",
      method: "POST",
      data,
    }),
};
