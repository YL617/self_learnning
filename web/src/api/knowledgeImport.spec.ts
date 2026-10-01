import { beforeEach, describe, expect, it, vi } from 'vitest'

const { httpMock } = vi.hoisted(() => ({
  httpMock: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

vi.mock('./http', () => ({ http: httpMock }))

import { importErrorMessage, knowledgeImportApi, readImportRejection } from './knowledgeImport'

function formOf(call = 0): FormData {
  return httpMock.post.mock.calls[call][1] as FormData
}

describe('knowledgeImportApi 契约', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    httpMock.post.mockResolvedValue({ data: {} })
    httpMock.get.mockResolvedValue({ data: [] })
  })

  it('preview 以 multipart 提交文件，且不混入 content', async () => {
    const file = new File(['学科,知识点名\n数据结构,栈'], 'kp.csv', { type: 'text/csv' })
    await knowledgeImportApi.preview({ file, conflict_strategy: 'update_empty' })

    expect(httpMock.post.mock.calls[0][0]).toBe('/knowledge-import/preview')
    const form = formOf()
    expect(form.get('file')).toBe(file)
    expect(form.get('conflict_strategy')).toBe('update_empty')
    expect(form.has('content')).toBe(false)
  })

  it('preview 支持粘贴入口：只带 content', async () => {
    await knowledgeImportApi.preview({ content: '学科\t知识点名\n数据结构\t栈' })

    const form = formOf()
    expect(form.get('content')).toBe('学科\t知识点名\n数据结构\t栈')
    expect(form.has('file')).toBe(false)
  })

  it('conflict_strategy 缺省为 skip（与后端默认一致，且不存在 overwrite）', async () => {
    await knowledgeImportApi.preview({ content: 'a' })
    expect(formOf().get('conflict_strategy')).toBe('skip')
  })

  it('preview 透传 source_name 供批次审计', async () => {
    await knowledgeImportApi.preview({ content: 'a', source_name: '文件导入 / kp.csv' })
    expect(formOf().get('source_name')).toBe('文件导入 / kp.csv')
  })

  it('apply 原样重传同一份数据，并带上 expected_total_rows 乐观锁', async () => {
    const file = new File(['x'], 'kp.tsv', { type: 'text/tab-separated-values' })
    await knowledgeImportApi.apply({
      file,
      conflict_strategy: 'skip',
      expected_total_rows: 32,
    })

    expect(httpMock.post.mock.calls[0][0]).toBe('/knowledge-import/apply')
    const form = formOf()
    expect(form.get('file')).toBe(file)
    expect(form.get('expected_total_rows')).toBe('32')
  })

  it('apply 未给 expected_total_rows 时不发送该字段（交由后端跳过乐观锁）', async () => {
    await knowledgeImportApi.apply({ content: 'a' })
    expect(formOf().has('expected_total_rows')).toBe(false)
  })

  it('batches 支持 status / limit / offset 分页参数', async () => {
    await knowledgeImportApi.batches({ status: 'applied', limit: 50, offset: 100 })
    expect(httpMock.get).toHaveBeenCalledWith('/knowledge-import/batches', {
      params: { status: 'applied', limit: 50, offset: 100 },
    })
  })

  it('batch / rollback 使用批次子路径', async () => {
    await knowledgeImportApi.batch(7)
    await knowledgeImportApi.rollback(7)
    expect(httpMock.get).toHaveBeenCalledWith('/knowledge-import/batches/7')
    expect(httpMock.post).toHaveBeenCalledWith('/knowledge-import/batches/7/rollback')
  })

  it('模板必须走 axios（blob），否则带不上管理员 token', async () => {
    await knowledgeImportApi.downloadTemplate()
    expect(httpMock.get).toHaveBeenCalledWith('/knowledge-import/template', {
      responseType: 'blob',
    })
  })
})

describe('导入错误体解析', () => {
  it('解析后端结构化 detail（400 / 409）', () => {
    const rejection = readImportRejection({
      response: {
        data: {
          detail: {
            message: '存在 2 行校验错误',
            code: 'A01',
            batch_errors: [{ row: null, level: 'error', code: 'B02', message: '缺少必需列' }],
            row_issues: [
              { row: 7, level: 'error', code: 'E09', field: 'name', message: '批内重复' },
            ],
            cycle: ['数据结构 > B', '数据结构 > A', '数据结构 > B'],
          },
        },
      },
    })

    expect(rejection?.message).toBe('存在 2 行校验错误')
    expect(rejection?.code).toBe('A01')
    expect(rejection?.batch_errors).toHaveLength(1)
    expect(rejection?.row_issues[0].row).toBe(7)
    expect(rejection?.cycle).toEqual(['数据结构 > B', '数据结构 > A', '数据结构 > B'])
  })

  it('缺失字段回退为空数组与 null，避免渲染崩溃', () => {
    const rejection = readImportRejection({ response: { data: { detail: { message: 'x' } } } })
    expect(rejection).toEqual({
      message: 'x',
      code: null,
      batch_errors: [],
      row_issues: [],
      cycle: [],
    })
  })

  it('纯字符串 detail 与网络错误都返回 null', () => {
    expect(readImportRejection({ response: { data: { detail: '批次不存在' } } })).toBeNull()
    expect(readImportRejection(new Error('Network Error'))).toBeNull()
  })

  it('importErrorMessage 对字符串 detail 原样展示，否则用兜底文案', () => {
    expect(importErrorMessage({ response: { data: { detail: '批次不存在' } } }, 'x')).toBe(
      '批次不存在',
    )
    expect(importErrorMessage(new Error('boom'), '导入失败')).toBe('导入失败')
    expect(
      importErrorMessage({ response: { data: { detail: { message: '成环' } } } }, '导入失败'),
    ).toBe('成环')
  })
})
