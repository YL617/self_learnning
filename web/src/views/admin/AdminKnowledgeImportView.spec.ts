import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  KnowledgeImportApplyResult,
  KnowledgeImportBatch,
  KnowledgeImportBatchDetail,
  KnowledgeImportPreview,
  KnowledgeImportPreviewRow,
  KnowledgeImportRejection,
} from '@/types'
import AdminKnowledgeImportView from './AdminKnowledgeImportView.vue'

const { apiMock, downloadBlobMock } = vi.hoisted(() => ({
  apiMock: {
    preview: vi.fn(),
    apply: vi.fn(),
    batches: vi.fn(),
    batch: vi.fn(),
    rollback: vi.fn(),
    downloadTemplate: vi.fn(),
  },
  downloadBlobMock: vi.fn(),
}))

// 只替换 api 对象本身，保留 readImportRejection / importErrorMessage 等真实实现。
vi.mock('@/api/knowledgeImport', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/knowledgeImport')>()
  return { ...actual, knowledgeImportApi: apiMock }
})
// 保留真实的 toCsvBlob（供内容断言），只拦截真正触发浏览器下载的动作。
vi.mock('@/utils/csvExport', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/utils/csvExport')>()
  return { ...actual, downloadBlob: downloadBlobMock }
})

// ---------------------------------------------------------------- fixtures

function row(overrides: Partial<KnowledgeImportPreviewRow> = {}): KnowledgeImportPreviewRow {
  return {
    row: 2,
    subject: '数据结构',
    parent_path: '线性表',
    name: '栈',
    code: 'DS.LINEAR.STACK',
    aliases: ['堆栈'],
    difficulty: 'medium',
    estimated_minutes: 20,
    node_type: 'concept',
    node_type_source: '知识点行',
    action: 'create',
    existing_kp_id: null,
    issues: [],
    ...overrides,
  }
}

function preview(overrides: Partial<KnowledgeImportPreview> = {}): KnowledgeImportPreview {
  return {
    source_format: 'csv',
    detected_encoding: 'utf-8',
    detected_delimiter: ',',
    has_header: true,
    total_rows: 4,
    error_rows: 0,
    warning_rows: 1,
    parse_notes: ['已剔除 1 个空行'],
    planned: { create: 32, create_concept: 32, create_container: 6, skip: 4, update_empty: 2, create_parent: 6 },
    new_subjects: [],
    parent_paths_to_create: ['线性表'],
    auto_parent_nodes: [
      { name: '线性表', path: '线性表', node_type: 'container', node_type_source: '由层级路径自动推导' },
    ],
    rows: [row(), row({ row: 3, name: '队列', issues: [] })],
    truncated: false,
    conflict_strategy: 'skip',
    can_apply: true,
    ...overrides,
  }
}

function batch(overrides: Partial<KnowledgeImportBatch> = {}): KnowledgeImportBatch {
  return {
    id: 12,
    user_id: 1,
    source_name: '文件导入 / kp.csv',
    source_format: 'csv',
    conflict_strategy: 'skip',
    status: 'applied',
    total_rows: 4,
    created_count: 3,
    updated_count: 0,
    skipped_count: 1,
    failed_count: 0,
    auto_parent_count: 1,
    error_summary: null,
    created_at: '2026-10-02T10:30:00',
    applied_at: '2026-10-02T10:30:00',
    rolled_back_at: null,
    ...overrides,
  }
}

// ---------------------------------------------------------------- helpers

function buttonByText(wrapper: VueWrapper<any>, text: string) {
  const target = text.replace(/\s+/g, '')
  return wrapper
    .findAll('button')
    .find((btn: any) => btn.text().replace(/\s+/g, '') === target)
}

function bodyRows(wrapper: VueWrapper<any>) {
  return wrapper.findAll('.imp-tr').filter((el: any) => !el.classes().includes('imp-th'))
}

function statValue(wrapper: VueWrapper<any>, label: string) {
  const card = wrapper
    .findAll('.imp-stats .stat-card')
    .find((el: any) => el.find('.stat-label').text() === label)
  return card?.find('.stat-value').text()
}

async function upload(wrapper: VueWrapper<any>, file: File) {
  const input = wrapper.find('input.imp-file-input')
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
  await input.trigger('change')
  await flushPromises()
}

async function setup(rows: KnowledgeImportBatch[] = []) {
  apiMock.batches.mockResolvedValue({ data: rows })
  const wrapper = mount(AdminKnowledgeImportView)
  await flushPromises()
  return wrapper as VueWrapper<any>
}

async function withPreview(wrapper: VueWrapper<any>, payload: KnowledgeImportPreview) {
  apiMock.preview.mockResolvedValue({ data: payload })
  await wrapper.find('.imp-paste').setValue('学科\t知识点名\n数据结构\t栈')
  await buttonByText(wrapper, '预览')!.trigger('click')
  await flushPromises()
}

describe('AdminKnowledgeImportView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.batches.mockResolvedValue({ data: [] })
    apiMock.batch.mockResolvedValue({ data: {} })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
  })

  // ---------------------------------------------------------- 输入方式
  it('上传 CSV 后以文件形式预览', async () => {
    const wrapper = await setup()
    await upload(wrapper, new File(['a'], 'kp.csv', { type: 'text/csv' }))

    expect(wrapper.text()).toContain('kp.csv')
    await buttonByText(wrapper, '预览')!.trigger('click')
    await flushPromises()

    const payload = apiMock.preview.mock.calls[0][0]
    expect(payload.file).toBeInstanceOf(File)
    expect(payload.file.name).toBe('kp.csv')
    expect(payload.content).toBeNull()
  })

  it('上传 TSV 与 XLSX 走同一条管线，文件名透传到 source_name', async () => {
    const wrapper = await setup()
    await upload(wrapper, new File(['a'], 'kp.tsv'))
    await buttonByText(wrapper, '预览')!.trigger('click')
    await flushPromises()
    expect(apiMock.preview.mock.calls[0][0].source_name).toBe('文件导入 / kp.tsv')

    const xlsx = await setup()
    await upload(xlsx, new File(['a'], 'kp.xlsx'))
    await buttonByText(xlsx, '预览')!.trigger('click')
    await flushPromises()
    expect(apiMock.preview.mock.calls[1][0].source_name).toBe('文件导入 / kp.xlsx')
  })

  it('拖拽不支持的后缀时给出明确提示且不设置文件', async () => {
    const wrapper = await setup()
    await wrapper.find('.imp-drop').trigger('drop', {
      dataTransfer: { files: [new File(['a'], 'old.xls')] },
    })
    expect(wrapper.text()).toContain('旧版 .xls 请先另存为 .xlsx')
    expect(wrapper.text()).toContain('点击或拖拽上传')
  })

  it('粘贴内容后预览，只带 content', async () => {
    const wrapper = await setup()
    // 尚未输入时按钮禁用，点了也不该发请求。
    expect(buttonByText(wrapper, '预览')!.attributes('disabled')).toBeDefined()
    await buttonByText(wrapper, '预览')!.trigger('click')
    await flushPromises()
    expect(apiMock.preview).not.toHaveBeenCalled()

    await wrapper.find('.imp-paste').setValue('学科\t知识点名\n数据结构\t栈')
    await buttonByText(wrapper, '预览')!.trigger('click')
    await flushPromises()

    expect(apiMock.preview).toHaveBeenCalledTimes(1)
    expect(apiMock.preview.mock.calls[0][0].content).toContain('数据结构')
    expect(apiMock.preview.mock.calls[0][0].file).toBeNull()
  })

  it('文件与粘贴互斥：选文件会清空粘贴框，粘贴会移除文件', async () => {
    const wrapper = await setup()
    await wrapper.find('.imp-paste').setValue('学科\t知识点名')
    await upload(wrapper, new File(['a'], 'kp.csv'))
    expect((wrapper.find('.imp-paste').element as HTMLTextAreaElement).value).toBe('')
    expect(wrapper.text()).toContain('kp.csv')

    await wrapper.find('.imp-paste').setValue('学科\t知识点名')
    await flushPromises()
    expect(wrapper.text()).toContain('点击或拖拽上传')
    expect(wrapper.text()).not.toContain('kp.csv')
  })

  // ---------------------------------------------------------- 冲突策略
  it('冲突策略默认为 skip，且界面上不存在 overwrite', async () => {
    const wrapper = await setup()
    const select = wrapper.find('.imp-strategy select')
    expect((select.element as HTMLSelectElement).value).toBe('skip')

    await wrapper.find('.imp-paste').setValue('a')
    await buttonByText(wrapper, '预览')!.trigger('click')
    await flushPromises()
    expect(apiMock.preview.mock.calls[0][0].conflict_strategy).toBe('skip')

    expect(select.findAll('option')).toHaveLength(2)
    expect(select.text()).not.toContain('覆盖')
    expect(select.text()).toContain('仅补齐既有知识点的空字段')
  })

  it('切换为 update_empty 后预览使用新策略', async () => {
    const wrapper = await setup()
    await wrapper.find('.imp-paste').setValue('a')
    await wrapper.find('.imp-strategy select').setValue('update_empty')
    await buttonByText(wrapper, '预览')!.trigger('click')
    await flushPromises()
    expect(apiMock.preview.mock.calls[0][0].conflict_strategy).toBe('update_empty')
  })

  // ---------------------------------------------------------- 预览展示
  it('预览后展示全部统计项', async () => {
    const wrapper = await setup()
    await withPreview(wrapper, preview())

    expect(statValue(wrapper, '总行数')).toBe('4')
    expect(statValue(wrapper, '将创建知识点')).toBe('32')
    expect(statValue(wrapper, '将自动创建目录')).toBe('6')
    expect(statValue(wrapper, '将跳过')).toBe('4')
    expect(statValue(wrapper, '将补空')).toBe('2')
    expect(statValue(wrapper, '错误数')).toBe('0')
    expect(statValue(wrapper, '警告数')).toBe('1')
    expect(wrapper.text()).toContain('已剔除 1 个空行')
  })

  it('逐行表格展示要求的十一列（含类型）', async () => {
    const wrapper = await setup()
    await withPreview(wrapper, preview())

    const header = wrapper.find('.imp-th').findAll('span').map((el: any) => el.text())
    expect(header).toEqual([
      '行号', '学科', '层级路径', '名称', '类型', '别名', '难度', '预计学时', '编码', '动作', '校验结论',
    ])

    const first = bodyRows(wrapper)[0]
    expect(first.text()).toContain('数据结构')
    expect(first.text()).toContain('线性表')
    expect(first.text()).toContain('知识点')
    expect(first.text()).toContain('堆栈')
    expect(first.text()).toContain('中等')
    expect(first.text()).toContain('20')
    expect(first.text()).toContain('DS.LINEAR.STACK')
    expect(first.text()).toContain('新建')
  })

  it('预览列出将自动创建的目录节点及其类型来源', async () => {
    const wrapper = await setup()
    await withPreview(wrapper, preview())

    expect(wrapper.text()).toContain('将自动创建 1 个目录节点')
    expect(wrapper.find('.imp-autoparent').text()).toContain('由层级路径自动推导')
  })

  it('error 行明显高亮，且与 warning 行可区分', async () => {
    const wrapper = await setup()
    await withPreview(
      wrapper,
      preview({
        error_rows: 1,
        warning_rows: 1,
        can_apply: false,
        rows: [
          row({ row: 2, issues: [{ row: 2, level: 'error', code: 'E09', message: '批内重复' }] }),
          row({ row: 3, name: '队列', issues: [{ row: 3, level: 'warning', code: 'W04', message: '层级过深' }] }),
          row({ row: 4, name: '链表' }),
        ],
      }),
    )

    const rows = bodyRows(wrapper)
    expect(rows[0].classes()).toContain('is-error')
    expect(rows[0].classes()).not.toContain('is-warning')
    expect(rows[1].classes()).toContain('is-warning')
    expect(rows[1].classes()).not.toContain('is-error')
    expect(rows[2].classes()).not.toContain('is-error')
    expect(rows[2].classes()).not.toContain('is-warning')

    expect(rows[0].text()).toContain('[E09]')
    expect(rows[1].text()).toContain('[W04]')
  })

  it('can_apply=false 时「执行导入」禁用并给出原因', async () => {
    const wrapper = await setup()
    await withPreview(wrapper, preview({ error_rows: 2, can_apply: false }))

    const applyBtn = buttonByText(wrapper, '执行导入')!
    expect(applyBtn.attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('存在 2 行校验错误，必须修正后重新预览才能执行导入')

    await applyBtn.trigger('click')
    await flushPromises()
    expect(apiMock.apply).not.toHaveBeenCalled()
  })

  it('can_apply=true 时「执行导入」可用', async () => {
    const wrapper = await setup()
    await withPreview(wrapper, preview())
    expect(buttonByText(wrapper, '执行导入')!.attributes('disabled')).toBeUndefined()
  })

  it('校验未通过时展示整批级问题、行级问题与完整环路径', async () => {
    const rejection: KnowledgeImportRejection = {
      message: '检测到层级成环',
      code: 'B04',
      batch_errors: [{ row: null, level: 'error', code: 'B02', message: '缺少必需列：知识点名' }],
      row_issues: [{ row: 7, level: 'error', code: 'E09', message: '本批重复' }],
      cycle: ['数据结构 > A', '数据结构 > B', '数据结构 > A'],
    }
    const wrapper = await setup()
    apiMock.preview.mockRejectedValue({ response: { data: { detail: rejection } } })

    await wrapper.find('.imp-paste').setValue('a')
    await buttonByText(wrapper, '预览')!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('校验未通过')
    expect(wrapper.text()).toContain('B04')
    expect(wrapper.text()).toContain('[B02] 缺少必需列：知识点名')
    expect(wrapper.text()).toContain('第 7 行：[E09] 本批重复')
    // 环路径必须是完整链路，而不是一句「存在循环」。
    expect(wrapper.find('.imp-cycle').text()).toBe('数据结构 > A → 数据结构 > B → 数据结构 > A')
  })

  it('预览行超过一页时提供分页，且每页 50 行', async () => {
    const wrapper = await setup()
    const many = Array.from({ length: 60 }, (_, index) =>
      row({ row: index + 2, name: `节点${index + 2}` }),
    )
    await withPreview(wrapper, preview({ rows: many, total_rows: 60 }))

    expect(bodyRows(wrapper)).toHaveLength(50)
    expect(wrapper.text()).toContain('第 1 / 2 页')

    await buttonByText(wrapper, '下一页')!.trigger('click')
    expect(bodyRows(wrapper)).toHaveLength(10)
    expect(wrapper.text()).toContain('第 2 / 2 页')
  })

  it('truncated 时提示仅展示部分行', async () => {
    const wrapper = await setup()
    await withPreview(wrapper, preview({ truncated: true, total_rows: 500 }))
    expect(wrapper.text()).toContain('实际共 500 行')
  })

  // ---------------------------------------------------------- apply
  it('执行导入前弹二次确认，并列出计划统计', async () => {
    const confirmMock = vi.mocked(window.confirm)
    const wrapper = await setup()
    apiMock.apply.mockResolvedValue({ data: { batch_id: 12 } as KnowledgeImportApplyResult })
    await withPreview(wrapper, preview())

    await buttonByText(wrapper, '执行导入')!.trigger('click')
    await flushPromises()

    const message = confirmMock.mock.calls[0][0] as string
    expect(message).toContain('新增知识点 32')
    expect(message).toContain('新增目录 6')
    expect(message).toContain('跳过 4')
    expect(message).toContain('补空 2')
    expect(message).toContain('是否确认？')
  })

  it('apply 重新上传同一份原始数据并带 expected_total_rows', async () => {
    const wrapper = await setup()
    apiMock.apply.mockResolvedValue({ data: { batch_id: 12 } as KnowledgeImportApplyResult })
    await withPreview(wrapper, preview({ total_rows: 32 }))

    await buttonByText(wrapper, '执行导入')!.trigger('click')
    await flushPromises()

    expect(apiMock.apply.mock.calls[0][0]).toMatchObject({
      content: '学科\t知识点名\n数据结构\t栈',
      conflict_strategy: 'skip',
      expected_total_rows: 32,
    })
  })

  it('二次确认取消时不发起 apply', async () => {
    vi.mocked(window.confirm).mockReturnValue(false)
    const wrapper = await setup()
    await withPreview(wrapper, preview())

    await buttonByText(wrapper, '执行导入')!.trigger('click')
    await flushPromises()
    expect(apiMock.apply).not.toHaveBeenCalled()
  })

  it('导入成功后展示结果统计，切到批次历史能看到刚写入的批次', async () => {
    const wrapper = await setup([batch()])
    apiMock.apply.mockResolvedValue({
      data: {
        batch_id: 12,
        status: 'applied',
        source_format: 'csv',
        conflict_strategy: 'skip',
        total_rows: 32,
        created_count: 30,
        created_concept_count: 30,
        created_container_count: 6,
        updated_count: 2,
        skipped_count: 4,
        failed_count: 0,
        auto_parent_count: 6,
        duration_ms: 180,
        rolled_back: false,
        rows: [row()],
      } as KnowledgeImportApplyResult,
    })

    await withPreview(wrapper, preview())
    await buttonByText(wrapper, '执行导入')!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('导入完成（批次 #12）')
    expect(statValue(wrapper, '新增知识点')).toBe('30')
    expect(statValue(wrapper, '新增目录')).toBe('6')
    expect(statValue(wrapper, '补空')).toBe('2')
    expect(statValue(wrapper, '跳过')).toBe('4')
    expect(statValue(wrapper, '耗时')).toBe('180 ms')

    await buttonByText(wrapper, '批次历史')!.trigger('click')
    await flushPromises()
    expect(apiMock.batches).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('文件导入 / kp.csv')
  })

  it('apply 失败时展示后端结构化中文错误，且不显示成功面板', async () => {
    const wrapper = await setup()
    apiMock.apply.mockRejectedValue({
      response: {
        data: {
          detail: { message: '数据已变化，请重新预览', code: 'A01', cycle: [] },
        },
      },
    })

    await withPreview(wrapper, preview())
    await buttonByText(wrapper, '执行导入')!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('数据已变化，请重新预览')
    expect(wrapper.text()).not.toContain('导入完成')
  })

  // ---------------------------------------------------------- 结果 CSV / 模板
  it('结果 CSV 在本地生成并做公式注入防护', async () => {
    const wrapper = await setup()
    apiMock.apply.mockResolvedValue({
      data: {
        batch_id: 12,
        status: 'applied',
        rows: [row({ name: '=cmd|calc', aliases: ['+A1'] })],
      } as KnowledgeImportApplyResult,
    })

    await withPreview(wrapper, preview())
    await buttonByText(wrapper, '执行导入')!.trigger('click')
    await flushPromises()
    await buttonByText(wrapper, '下载本批结果 CSV')!.trigger('click')
    await flushPromises()

    expect(downloadBlobMock).toHaveBeenCalledWith(expect.any(Blob), 'knowledge-import-12.csv')
    const text = await (downloadBlobMock.mock.calls[0][0] as Blob).text()
    expect(text).toContain("'=cmd|calc")
    expect(text).toContain("'+A1")
    expect(text).toContain('行号,学科,层级路径,名称')
  })

  it('下载模板走 blob 接口', async () => {
    const wrapper = await setup()
    apiMock.downloadTemplate.mockResolvedValue({ data: new Blob(['x']) })

    await buttonByText(wrapper, '下载模板')!.trigger('click')
    await flushPromises()

    expect(apiMock.downloadTemplate).toHaveBeenCalledTimes(1)
    expect(downloadBlobMock).toHaveBeenCalledWith(expect.any(Blob), 'knowledge_points_template.csv')
  })

  it('模板下载失败时提示中文错误', async () => {
    const wrapper = await setup()
    apiMock.downloadTemplate.mockRejectedValue({
      response: { data: { detail: '登录状态无效或已过期' } },
    })
    await buttonByText(wrapper, '下载模板')!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('登录状态无效或已过期')
  })

  // ---------------------------------------------------------- 批次历史
  it('批次历史展示全部要求的列与状态', async () => {
    const wrapper = await setup([
      batch(),
      batch({ id: 11, status: 'failed', failed_count: 4, source_format: 'xlsx' }),
      batch({ id: 10, status: 'rolled_back' }),
    ])

    await buttonByText(wrapper, '批次历史')!.trigger('click')
    await flushPromises()

    const header = wrapper.find('.imp-tr-batch.imp-th').findAll('span').map((el: any) => el.text())
    expect(header).toEqual([
      '时间', '操作人', '来源', '格式', '策略', '总行数', '新增', '更新', '跳过', '失败',
      '父节点', '状态', '操作',
    ])

    const rows = wrapper.findAll('.imp-tr-batch').filter((el: any) => !el.classes().includes('imp-th'))
    expect(rows).toHaveLength(3)
    expect(rows[0].text()).toContain('2026-10-02 10:30')
    expect(rows[0].text()).toContain('文件导入 / kp.csv')
    expect(rows[0].text()).toContain('已应用')
    expect(rows[1].text()).toContain('失败')
    expect(rows[2].text()).toContain('已回滚')
  })

  it('查看详情会拉取批次详情并展示本批知识点', async () => {
    const detail: KnowledgeImportBatchDetail = {
      ...batch(),
      knowledge_points: [
        { id: 1, name: '栈', subject: '数据结构' },
        { id: 2, name: '队列', subject: '数据结构' },
      ],
      blocking_references: [],
      notes: [],
    }
    const wrapper = await setup([batch()])
    apiMock.batch.mockResolvedValue({ data: detail })

    await buttonByText(wrapper, '批次历史')!.trigger('click')
    await buttonByText(wrapper, '查看详情')!.trigger('click')
    await flushPromises()

    expect(apiMock.batch).toHaveBeenCalledWith(12)
    expect(wrapper.text()).toContain('批次 #12 详情')
    expect(wrapper.text()).toContain('数据结构 / 栈')
    expect(wrapper.text()).toContain('未检测到外部引用')
  })

  it('存在阻塞引用时列出原因并禁止回滚', async () => {
    const wrapper = await setup([batch()])
    apiMock.batch.mockResolvedValue({
      data: {
        ...batch(),
        knowledge_points: [{ id: 1, name: '栈', subject: '数据结构' }],
        blocking_references: [
          {
            knowledge_point_id: 1,
            knowledge_point_name: '栈',
            reason: 'linked_question',
            detail: '已被 2 道题目关联',
          },
          {
            knowledge_point_id: 1,
            knowledge_point_name: '栈',
            reason: 'has_children',
            detail: '存在批次外的子知识点',
          },
        ],
        notes: [],
      } as KnowledgeImportBatchDetail,
    })

    await buttonByText(wrapper, '批次历史')!.trigger('click')
    await buttonByText(wrapper, '查看详情')!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('无法回滚')
    expect(wrapper.text()).toContain('已被题目关联')
    expect(wrapper.text()).toContain('仍有子知识点')
    expect(wrapper.text()).toContain('已被 2 道题目关联')

    const rollbackBtn = buttonByText(wrapper, '回滚本批')!
    expect(rollbackBtn.attributes('disabled')).toBeDefined()
    await rollbackBtn.trigger('click')
    await flushPromises()
    expect(apiMock.rollback).not.toHaveBeenCalled()
  })

  it('回滚确认必须说明 update_empty 补空的字段不会被还原', async () => {
    const wrapper = await setup([batch({ updated_count: 2 })])
    apiMock.batch.mockResolvedValue({
      data: {
        ...batch({ updated_count: 2 }),
        knowledge_points: [{ id: 1, name: '栈', subject: '数据结构' }],
        blocking_references: [],
        notes: ['回滚不会清空 update_empty 补充的内容。'],
      } as KnowledgeImportBatchDetail,
    })
    apiMock.rollback.mockResolvedValue({
      data: { batch_id: 12, deleted_count: 3, kept_updated_count: 2, status: 'rolled_back', rolled_back_at: '2026-10-02T11:00:00' },
    })

    await buttonByText(wrapper, '批次历史')!.trigger('click')
    await buttonByText(wrapper, '查看详情')!.trigger('click')
    await flushPromises()
    await buttonByText(wrapper, '回滚本批')!.trigger('click')
    await flushPromises()

    const message = vi.mocked(window.confirm).mock.calls.at(-1)![0] as string
    expect(message).toContain('本次通过 update_empty 补充的字段不会被还原为空值')
    expect(message).toContain('并非完全可逆')

    expect(apiMock.rollback).toHaveBeenCalledWith(12)
    expect(wrapper.text()).toContain('已回滚批次 #12，删除 3 个知识点')
    expect(wrapper.text()).toContain('2 条补空字段保留原值（不会清空）')
  })

  it('回滚被后端拒绝（409 存在阻塞）时展示后端文案', async () => {
    const wrapper = await setup([batch()])
    apiMock.batch.mockResolvedValue({
      data: { ...batch(), knowledge_points: [], blocking_references: [], notes: [] } as KnowledgeImportBatchDetail,
    })
    apiMock.rollback.mockRejectedValue({
      response: { data: { detail: '知识点已被题目关联，无法回滚' } },
    })

    await buttonByText(wrapper, '批次历史')!.trigger('click')
    await buttonByText(wrapper, '查看详情')!.trigger('click')
    await flushPromises()
    await buttonByText(wrapper, '回滚本批')!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('知识点已被题目关联，无法回滚')
  })

  it('已回滚 / 失败的批次不允许再次回滚', async () => {
    const wrapper = await setup([batch({ id: 10, status: 'rolled_back' })])
    apiMock.batch.mockResolvedValue({
      data: {
        ...batch({ id: 10, status: 'rolled_back' }),
        knowledge_points: [],
        blocking_references: [],
        notes: [],
      } as KnowledgeImportBatchDetail,
    })

    await buttonByText(wrapper, '批次历史')!.trigger('click')
    await buttonByText(wrapper, '查看详情')!.trigger('click')
    await flushPromises()

    expect(buttonByText(wrapper, '回滚本批')!.attributes('disabled')).toBeDefined()
  })

  it('批次列表为空时展示空态', async () => {
    const wrapper = await setup([])
    await buttonByText(wrapper, '批次历史')!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('还没有导入批次')
  })
})
