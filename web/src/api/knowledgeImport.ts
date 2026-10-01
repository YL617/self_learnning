import { http } from './http'
import type {
  KnowledgeImportApplyResult,
  KnowledgeImportBatch,
  KnowledgeImportBatchDetail,
  KnowledgeImportConflictStrategy,
  KnowledgeImportPreview,
  KnowledgeImportRejection,
  KnowledgeImportRollbackResult,
} from '@/types'

export interface KnowledgeImportRequest {
  file?: File | null
  content?: string | null
  conflict_strategy?: KnowledgeImportConflictStrategy
  source_name?: string | null
}

export interface KnowledgeImportApplyRequest extends KnowledgeImportRequest {
  // 乐观锁：preview 时的总行数。与服务端重新解析的结果不一致就 409，
  // 防止「预览后用户又改了表格」导致执行了非本意的内容。
  expected_total_rows?: number | null
}

export interface KnowledgeImportBatchParams {
  status?: string
  limit?: number
  offset?: number
}

// 上传与粘贴共用一份 multipart 表单。**不要**手工设置 Content-Type，
// 交给浏览器补 boundary，否则服务端收不到 file 字段。
function buildForm(
  request: KnowledgeImportRequest,
  expectedTotalRows?: number | null,
): FormData {
  const form = new FormData()
  if (request.file) form.append('file', request.file)
  if (request.content) form.append('content', request.content)
  form.append('conflict_strategy', request.conflict_strategy ?? 'skip')
  if (request.source_name) form.append('source_name', request.source_name)
  if (expectedTotalRows !== undefined && expectedTotalRows !== null) {
    form.append('expected_total_rows', String(expectedTotalRows))
  }
  return form
}

export const knowledgeImportApi = {
  // dry-run：服务端只解析 + 校验 + 出计划，不写任何表、不落盘。
  preview: (request: KnowledgeImportRequest) =>
    http.post<KnowledgeImportPreview>('/knowledge-import/preview', buildForm(request)),

  // 重新上传同一份原始数据（服务端不留临时文件），完整校验后单事务写入。
  apply: (request: KnowledgeImportApplyRequest) =>
    http.post<KnowledgeImportApplyResult>(
      '/knowledge-import/apply',
      buildForm(request, request.expected_total_rows),
    ),

  batches: (params?: KnowledgeImportBatchParams) =>
    http.get<KnowledgeImportBatch[]>('/knowledge-import/batches', { params }),
  batch: (batchId: number) =>
    http.get<KnowledgeImportBatchDetail>(`/knowledge-import/batches/${batchId}`),
  rollback: (batchId: number) =>
    http.post<KnowledgeImportRollbackResult>(`/knowledge-import/batches/${batchId}/rollback`),

  // 模板接口同样挂管理员鉴权，所以必须走 axios 才能带上 Bearer token ——
  // 直接用 <a href> 下载会拿到 401。
  downloadTemplate: () =>
    http.get<Blob>('/knowledge-import/template', { responseType: 'blob' }),
}

// 把后端 400/409 的结构化 detail 解析出来；纯字符串 detail 或网络错误返回 null。
export function readImportRejection(error: unknown): KnowledgeImportRejection | null {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data
    ?.detail
  if (!detail || typeof detail !== 'object') return null
  const payload = detail as Partial<KnowledgeImportRejection>
  return {
    message: typeof payload.message === 'string' && payload.message ? payload.message : '导入失败',
    code: payload.code ?? null,
    batch_errors: payload.batch_errors ?? [],
    row_issues: payload.row_issues ?? [],
    cycle: payload.cycle ?? [],
  }
}

export function importErrorMessage(error: unknown, fallback: string): string {
  const rejection = readImportRejection(error)
  if (rejection) return rejection.message
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data
    ?.detail
  return typeof detail === 'string' && detail ? detail : fallback
}
