export interface UserProfile {
  major?: string | null
  grade?: string | null
  goals?: string | null
  daily_study_minutes: number
  weak_subjects?: string | null
  school_level?: string | null
  pain_point?: string | null
  learning_style?: string | null
  weekly_study_minutes: number
  available_time_slots?: string | null
  onboarding_completed: boolean
  onboarding_completed_at?: string | null
}

export interface User {
  id: number
  email: string
  username: string
  membership_level: string
  profile?: UserProfile | null
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user: User
}

export interface PlanItem {
  id: number
  plan_id: number
  title: string
  subject?: string | null
  scheduled_date: string
  duration_minutes: number
  completed: boolean
  order_index: number
}

export interface StudyPlan {
  id: number
  title: string
  goal?: string | null
  start_date: string
  end_date: string
  status: string
  created_at: string
  items: PlanItem[]
}

export interface PlanGenerateRequest {
  major: string
  grade: string
  goal: string
  daily_minutes: number
  weeks: number
  subjects: string[]
}

export interface StudyPlanCreate {
  title: string
  goal?: string
  start_date: string
  end_date: string
}

export interface PlanChatMessage {
  id: number
  role: string
  content: string
  created_at: string
}

export interface PlanChatStart {
  session_id: number
  reply: string
  status: string
}

export interface PlanChatReply {
  session_id: number
  reply: string
  status: string
  draft?: PlanDraft | null
}

export interface PlanDraft {
  title: string
  goal?: string | null
  items: PlanItem[]
}

export interface PlanChatConfirm {
  plan_id: number
  message: string
}

export interface OnboardingPayload {
  major?: string
  grade?: string
  goals: string[]
  weekly_minutes?: number
  learning_style: string[]
  pain_point: string[]
  school_level?: string
  available_time_slots: string[]
  generate_plan: boolean
  complete: boolean
}

export interface OnboardingResponse {
  profile: UserProfile
  plan?: StudyPlan | null
}

export interface Question {
  id: number
  subject: string
  knowledge_point: string
  question_type: string
  stem: string
  options_json?: string | null
  answer: string
  analysis?: string | null
  source: string
  is_favorite: boolean
}

export interface AnswerRecord {
  id: number
  question_id: number
  user_answer: string
  is_correct: boolean
  created_at: string
}

export interface WrongBookItem {
  id: number
  question_id: number
  review_count: number
  mastered: boolean
  created_at: string
  question?: Question | null
}

export interface DocumentItem {
  id: number
  filename: string
  file_type: string
  storage_path: string
  status: string
  chunks_count: number
  created_at: string
}

export interface FocusSession {
  id: number
  task_label: string
  started_at: string
  ended_at?: string | null
  duration_minutes: number
  completed: boolean
}

export interface FocusStats {
  total_minutes: number
  session_count: number
  today_minutes: number
}

export interface Pet {
  id: number
  name: string
  level: number
  exp: number
  mood: number
}

export interface CoinTransaction {
  id: number
  amount: number
  reason: string
  created_at: string
}
