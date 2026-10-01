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

import { knowledgePointsApi, toKnowledgePointNameMap } from './knowledgePoints'

describe('knowledgePointsApi 契约', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('list 支持 subject / parent_id / q 查询参数', async () => {
    httpMock.get.mockResolvedValue({ data: [] })
    await knowledgePointsApi.list({ subject: '数据结构', q: '栈' })
    expect(httpMock.get).toHaveBeenCalledWith('/knowledge-points', {
      params: { subject: '数据结构', q: '栈' },
    })
  })

  it('list 无参数时不传 params', async () => {
    httpMock.get.mockResolvedValue({ data: [] })
    await knowledgePointsApi.list()
    expect(httpMock.get).toHaveBeenCalledWith('/knowledge-points', { params: undefined })
  })

  it('get / questions 使用知识点子路径', async () => {
    httpMock.get.mockResolvedValue({ data: null })
    await knowledgePointsApi.get(5)
    await knowledgePointsApi.questions(5)
    expect(httpMock.get).toHaveBeenNthCalledWith(1, '/knowledge-points/5')
    expect(httpMock.get).toHaveBeenNthCalledWith(2, '/knowledge-points/5/questions')
  })

  it('create 使用 POST /knowledge-points', async () => {
    httpMock.post.mockResolvedValue({ data: null })
    await knowledgePointsApi.create({ name: '栈', subject: '数据结构' })
    expect(httpMock.post).toHaveBeenCalledWith('/knowledge-points', {
      name: '栈',
      subject: '数据结构',
    })
  })

  it('update 使用 PATCH /knowledge-points/{id}', async () => {
    httpMock.patch.mockResolvedValue({ data: null })
    await knowledgePointsApi.update(9, { name: '队列' })
    expect(httpMock.patch).toHaveBeenCalledWith('/knowledge-points/9', { name: '队列' })
  })

  it('remove 使用 DELETE /knowledge-points/{id}', async () => {
    httpMock.delete.mockResolvedValue({ data: undefined })
    await knowledgePointsApi.remove(9)
    expect(httpMock.delete).toHaveBeenCalledWith('/knowledge-points/9')
  })
})

describe('toKnowledgePointNameMap', () => {
  it('构建 id -> name 映射', () => {
    const map = toKnowledgePointNameMap([
      { id: 1, name: '栈' },
      { id: 2, name: '队列' },
    ] as any)
    expect(map).toEqual({ 1: '栈', 2: '队列' })
  })
})
