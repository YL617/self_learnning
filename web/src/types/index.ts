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
  nickname?: string | null
  avatar_url?: string | null
  membership_level: string
  membership_expires_at?: string | null
  role?: string
  is_admin?: boolean
  profile?: UserProfile | null
}

export interface MembershipInfo {
  membership_level: string
  effective_membership: string
  membership_expires_at?: string | null
  trial_active: boolean
  trial_days_left: number
  ai_quota_used: number
  ai_quota_total: number
}

export interface ActivationCode {
  id: number
  code: string
  tier: string
  days: number
  status: string
  used_by?: number | null
  used_at?: string | null
  created_at: string
}

export interface AdminUser {
  id: number
  email: string
  username: string
  nickname?: string | null
  membership_level: string
  membership_expires_at?: string | null
  role: string
  is_active: boolean
  created_at: string
}

export interface AiMonitorSnapshot {
  id: number
  provider: string
  total_balance: string
  granted_balance: string
  topped_up_balance: string
  is_available: boolean
  status: string
  error_message?: string | null
  checked_at: string
}

export interface AiUsage {
  id: number
  provider: string
  usage_date: string
  tokens: number
  cost: number
  recorded_at: string
}

export interface AiMonitorState {
  provider: string
  snapshot?: AiMonitorSnapshot | null
  usage: AiUsage[]
  is_low_balance?: boolean
  low_balance_threshold?: number
}

export interface StatsOverview {
  user_count: number
  active_today: number
  plan_count: number
  question_count: number
  wrong_book_count: number
  document_count: number
  course_count: number
  total_focus_minutes: number
  total_coins_issued: number
  ai_monitor?: AiMonitorState | null
}

export interface AdminQuestion {
  id: number
  user_id: number
  subject: string
  knowledge_point: string
  question_type: string
  stem: string
  source: string
  is_favorite: boolean
  created_at: string
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
  difficulty: string
  suggested_time_slot?: string | null
  buffer_minutes: number
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
  known: string[]
}

export interface PlanChatReply {
  session_id: number
  reply: string
  status: string
  draft?: PlanDraft | null
  known: string[]
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

export interface KnowledgePoint {
  id: number
  name: string
  normalized_name: string
  subject: string
  parent_id?: number | null
  description?: string | null
  status: string
  source: string
  // P0 node_type：container=目录（只组织层级），concept=可学习知识点。
  // 后端 NOT NULL + server_default='concept'，历史数据均为 concept。
  node_type: KnowledgePointNodeType
  // 大阶段 4 M1：知识库内容元数据（全部可空，历史知识点不会有值）。
  // difficulty 只用于展示、排序与推荐；掌握度的难度系数来自作答记录，与它无关。
  code?: string | null
  aliases?: string[] | null
  difficulty?: KnowledgePointDifficulty | null
  estimated_minutes?: number | null
  import_batch_id?: number | null
  created_at: string
  updated_at: string
}

// 与后端 knowledge_points.node_type 的 CHECK 词表一致：全项目只有这一套。
export type KnowledgePointNodeType = 'container' | 'concept'

export const NODE_TYPE_LABELS: Record<KnowledgePointNodeType, string> = {
  container: '目录',
  concept: '知识点',
}

export const NODE_TYPE_ICONS: Record<KnowledgePointNodeType, string> = {
  container: '📁',
  concept: '🧠',
}

// 与后端 knowledge_points.difficulty 的 CHECK 词表一致：全项目只有这一套。
export type KnowledgePointDifficulty = 'easy' | 'medium' | 'hard'

export const DIFFICULTY_LABELS: Record<KnowledgePointDifficulty, string> = {
  easy: '简单',
  medium: '中等',
  hard: '困难',
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

// Phase 2：题目 ↔ 知识点结构化关联。
// 后端 QuestionKnowledgePointRead 不含嵌套知识点对象，前端需用 KnowledgePoint 列表按 id 解析名称。
export interface QuestionKnowledgePoint {
  id: number
  question_id: number
  knowledge_point_id: number
  role: 'primary' | 'secondary' | string
  source: string
  created_at: string
}

// 已解析名称的关联标签（供题目卡片展示）。
export interface KnowledgePointTag {
  id: number
  name: string
  role: string
}

export interface AnswerRecord {
  id: number
  question_id: number
  user_answer: string
  is_correct: boolean
  created_at: string
}

// 大阶段 2：用户维度的知识点掌握度（后端确定性算法维护，只读）。
export interface KnowledgePointBrief {
  id: number
  name: string
  subject: string
  parent_id?: number | null
  // P0：容器不会出现在掌握度 / 推荐里，但保留字段以便前端做防御性判断。
  node_type?: KnowledgePointNodeType | null
  // 大阶段 4 M1：可选展示字段（推荐与今日建议会用到）。
  difficulty?: KnowledgePointDifficulty | null
  estimated_minutes?: number | null
}

export interface KnowledgePointMastery {
  id: number
  knowledge_point_id: number
  mastery_score: number
  attempt_count: number
  correct_count: number
  correct_streak: number
  last_answered_at?: string | null
  last_correct_at?: string | null
  last_reviewed_at?: string | null
  created_at: string
  updated_at: string
  knowledge_point?: KnowledgePointBrief | null
}

export interface MasterySummary {
  total: number
  weak_count: number
  average_score: number
  today_review_count: number
  weak_threshold: number
}

export interface WrongBookItem {
  id: number
  question_id: number
  review_count: number
  mastered: boolean
  review_stage: number
  next_review_date?: string | null
  last_reviewed_at?: string | null
  created_at: string
  question?: Question | null
}

// 大阶段 3：知识点前置依赖（DAG）。与 parent_id（归属层级树）语义不同：
// parent_id 表达「属于」，prerequisite 表达「必须先学」。
export interface PrerequisiteItem {
  id: number
  knowledge_point_id: number
  prerequisite_id: number
  strength: number
  source: string
  status: string
  note?: string | null
  created_at: string
  updated_at: string
  prerequisite?: KnowledgePointBrief | null
  // 针对当前用户：该前置是否已满足 / 是否构成硬性阻塞
  satisfied?: boolean | null
  blocking?: boolean | null
}

export interface PrerequisiteDetail {
  knowledge_point: KnowledgePointBrief
  ready: boolean
  threshold: number
  items: PrerequisiteItem[]
}

export interface LearningPathStep {
  order: number
  knowledge_point: KnowledgePointBrief
  mastery_score?: number | null
  satisfied: boolean
  is_target: boolean
}

export interface LearningPath {
  target: KnowledgePointBrief
  ready: boolean
  threshold: number
  steps: LearningPathStep[]
}

export interface PrerequisiteSuggestion {
  prerequisite_id: number
  prerequisite_name: string
  reason: string
  confidence: number
}

export interface PrerequisiteSuggestResult {
  knowledge_point: KnowledgePointBrief
  suggestions: PrerequisiteSuggestion[]
  note?: string | null
}

// 大阶段 3：今日学习建议（后端确定性规则引擎生成，只读展示，不写入学习计划）。
export type RecommendationAction =
  | 'review_wrong'
  | 'review_weak'
  | 'learn_new'
  | 'practice'

export interface RecommendationItem {
  action: RecommendationAction
  action_label: string
  knowledge_point_id: number
  knowledge_point_name: string
  subject: string
  score: number
  reason: string
  order: number
  estimated_minutes: number
  // 打分分解项（base/urgency/gap/goal/unlock/recency），用于核对"为什么推荐这个"
  components: Record<string, number>
  question_ids: number[]
}

export interface RecommendationToday {
  date: string
  weak_threshold: number
  ready_threshold: number
  items: RecommendationItem[]
}

export interface DocumentItem {
  id: number
  filename: string
  file_type: string
  storage_path: string
  status: string
  chunks_count: number
  size_bytes: number
  temp_cleanup_at?: string | null
  created_at: string
}

export interface FocusSession {
  id: number
  task_label: string
  started_at: string
  ended_at?: string | null
  duration_minutes: number
  completed: boolean
  tag_color?: string | null
}

export interface FocusTag {
  id: number
  name: string
  color: string
  created_at: string
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
  hunger: number
  evolution_stage: number
  runaway: boolean
  play_count_today: number
  playing_until?: string | null
  last_fed_at?: string | null
}

export interface PetPlaySession {
  id: number
  status: string
  started_at: string
  ended_at?: string | null
  duration_minutes: number
  coin_cost: number
  mood_gain: number
  exp_gain: number
  hunger_loss: number
  created_at: string
}

export interface PetPlaySummary {
  elapsed_minutes: number
  mood_gain: number
  exp_gain: number
  hunger_loss: number
  coins_spent: number
  message: string
}

export interface PetPlayState {
  session?: PetPlaySession | null
  summary?: PetPlaySummary | null
  pet: Pet
}

export interface PetMessage {
  id: number
  role: string
  kind: string
  content: string
  created_at: string
}

export interface PetChatReply {
  reply: string
  pet: Pet
  messages: PetMessage[]
}

export interface PetInteraction {
  reply: string
  pet: Pet
}

export interface CoinTransaction {
  id: number
  amount: number
  reason: string
  created_at: string
}

export interface Todo {
  id: number
  title: string
  due_date: string
  completed: boolean
}

export interface Reminder {
  id: number
  title: string
  remind_at: string
  triggered: boolean
  dismissed: boolean
}

export interface NotificationItem {
  id: number
  kind: string
  title: string
  remind_at?: string | null
}

export interface CalendarEvent {
  date: string
  title: string
  kind: string
  id: number
  completed: boolean
}

export interface CourseChapter {
  id: number
  title: string
  order_index: number
}

export interface Course {
  id: number
  title: string
  platform: string
  url: string
  description?: string | null
  category?: string | null
  level?: string | null
  language?: string | null
  health_status?: string | null
  health_checked_at?: string | null
  health_error?: string | null
  dismiss_count?: number
  save_count?: number
  chapters: CourseChapter[]
}

export interface CourseRecommendation {
  id: number
  plan_id?: number | null
  course_id?: number | null
  title: string
  platform: string
  url: string
  description?: string | null
  subject?: string | null
  category?: string | null
  level?: string | null
  language?: string | null
  health_status?: string | null
  status: string
  created_at: string
}

export interface WeeklyReport {
  start_date: string
  end_date: string
  focus_minutes: number
  sessions: number
  answered: number
  correct: number
  coins_earned: number
  wrong_added: number
}

// ---------------------------------------------------------------- 批量知识库导入
// 大阶段 4 M2 的 6 个接口契约（前端侧镜像）。词表与后端 Literal 一一对应，
// 后端 CHECK 约束已经钉死这些取值，前端不要自造新值。

export type KnowledgeImportSourceFormat = 'tsv' | 'csv' | 'xlsx' | 'paste'
// 刻意没有 overwrite：导入永不覆盖既有非空字段。
export type KnowledgeImportConflictStrategy = 'skip' | 'update_empty'
export type KnowledgeImportBatchStatus = 'applied' | 'failed' | 'rolled_back'
export type KnowledgeImportRowAction = 'create' | 'skip' | 'update_empty'
export type KnowledgeImportIssueLevel = 'error' | 'warning'

// row 为 null 表示整批级结论（B 系列）；行级结论用 1-based 源行号。
export interface KnowledgeImportIssue {
  row: number | null
  level: KnowledgeImportIssueLevel
  code: string
  field?: string | null
  message: string
}

export interface KnowledgeImportPreviewRow {
  row: number
  subject: string
  parent_path?: string | null
  name: string
  code?: string | null
  aliases: string[]
  difficulty?: string | null
  estimated_minutes?: number | null
  // P0：本行将成为哪种节点。行「知识点名」= concept；层级路径自动创建 = container。
  node_type: KnowledgePointNodeType
  node_type_source?: string | null
  action: KnowledgeImportRowAction
  existing_kp_id?: number | null
  issues: KnowledgeImportIssue[]
}

// P0：预览里显式列出的「将自动创建的目录节点」。
export interface KnowledgeImportAutoParentNode {
  name: string
  path: string
  node_type: KnowledgePointNodeType
  node_type_source?: string | null
}

export interface KnowledgeImportPlanCounts {
  create?: number
  skip?: number
  update_empty?: number
  create_parent?: number
  // P0：知识点与目录分开计数，不要混成一个 create。
  create_concept?: number
  create_container?: number
}

export interface KnowledgeImportPreview {
  source_format: KnowledgeImportSourceFormat
  detected_encoding?: string | null
  detected_delimiter?: string | null
  has_header: boolean
  total_rows: number
  error_rows: number
  warning_rows: number
  parse_notes: string[]
  planned: KnowledgeImportPlanCounts
  new_subjects: string[]
  parent_paths_to_create: string[]
  // P0：将自动创建的目录节点（含类型来源）。
  auto_parent_nodes: KnowledgeImportAutoParentNode[]
  rows: KnowledgeImportPreviewRow[]
  truncated: boolean
  conflict_strategy: KnowledgeImportConflictStrategy
  can_apply: boolean
}

// 400 / 409 的结构化错误体（后端 HTTPException.detail）。
export interface KnowledgeImportRejection {
  message: string
  code?: string | null
  batch_errors: KnowledgeImportIssue[]
  row_issues: KnowledgeImportIssue[]
  cycle: string[]
}

export interface KnowledgeImportApplyResult {
  batch_id: number
  status: 'applied' | 'failed'
  source_format: string
  conflict_strategy: string
  total_rows: number
  created_count: number
  // P0：知识点与目录分开计数。
  created_concept_count: number
  created_container_count: number
  updated_count: number
  skipped_count: number
  failed_count: number
  auto_parent_count: number
  duration_ms: number
  rolled_back: boolean
  rows: KnowledgeImportPreviewRow[]
}

export interface KnowledgeImportBatch {
  id: number
  user_id?: number | null
  source_name?: string | null
  source_format: string
  conflict_strategy: string
  status: KnowledgeImportBatchStatus | string
  total_rows: number
  created_count: number
  updated_count: number
  skipped_count: number
  failed_count: number
  auto_parent_count: number
  error_summary?: string | null
  created_at: string
  applied_at?: string | null
  rolled_back_at?: string | null
}

export type KnowledgeImportBlockingReason =
  | 'has_children'
  | 'linked_question'
  | 'has_mastery'
  | 'prerequisite_edge'

export interface KnowledgeImportBlockingRef {
  knowledge_point_id: number
  knowledge_point_name: string
  reason: KnowledgeImportBlockingReason
  detail: string
}

export interface KnowledgeImportBatchDetail extends KnowledgeImportBatch {
  knowledge_points: KnowledgePointBrief[]
  blocking_references: KnowledgeImportBlockingRef[]
  notes: string[]
}

export interface KnowledgeImportRollbackResult {
  batch_id: number
  deleted_count: number
  // update_empty 补过、但回滚不会清空的条数（M2 已接受的局限）。
  kept_updated_count: number
  status: 'rolled_back'
  rolled_back_at: string
}
