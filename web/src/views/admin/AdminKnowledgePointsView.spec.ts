import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { knowledgePointsApi } from '@/api/knowledgePoints'
import type { KnowledgePoint } from '@/types'
import AdminKnowledgePointsView from './AdminKnowledgePointsView.vue'

vi.mock('@/api/knowledgePoints', () => ({
  knowledgePointsApi: {
    list: vi.fn(),
    get: vi.fn(),
    questions: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    prerequisites: vi.fn(),
    addPrerequisite: vi.fn(),
    removePrerequisite: vi.fn(),
    learningPath: vi.fn(),
    suggestPrerequisites: vi.fn(),
  },
}))

function kp(id: number, name: string, overrides: Partial<KnowledgePoint> = {}): KnowledgePoint {
  return {
    id,
    name,
    normalized_name: name.toLowerCase(),
    subject: '数据结构',
    parent_id: null,
    description: null,
    status: 'active',
    source: 'admin',
    node_type: 'concept',
    created_at: '2026-10-01T00:00:00',
    updated_at: '2026-10-01T00:00:00',
    ...overrides,
  }
}

const fixtures: KnowledgePoint[] = [
  kp(1, '线性表'),
  kp(2, '栈', { parent_id: 1 }),
  kp(3, '顺序栈', { parent_id: 2 }),
  kp(4, '进程', { subject: '操作系统', source: 'system', status: 'pending' }),
]

async function setup(items: KnowledgePoint[] = fixtures) {
  vi.mocked(knowledgePointsApi.list).mockResolvedValue({ data: items } as any)
  const wrapper = mount(AdminKnowledgePointsView)
  await flushPromises()
  return wrapper as VueWrapper<any>
}

function bodyRows(wrapper: VueWrapper<any>) {
  return wrapper.findAll('.kp-tr').filter((row: any) => !row.classes().includes('kp-th'))
}

// P0：名称/父级选项前会带上类型图标（📁/🧠），断言前统一剥掉。
function cleanText(text: string): string {
  return text.replace(/[└📁🧠]/g, '').trim()
}

function rowByName(wrapper: VueWrapper<any>, name: string) {
  return bodyRows(wrapper).find((row: any) => cleanText(row.find('.kp-name').text()) === name)
}

function buttonByText(wrapper: VueWrapper<any>, text: string) {
  return wrapper.findAll('button').find((btn: any) => btn.text().includes(text))
}

function formField(wrapper: VueWrapper<any>, index: number) {
  return wrapper.findAll('.form-grid .field')[index]
}

describe('AdminKnowledgePointsView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    vi.mocked(knowledgePointsApi.prerequisites).mockResolvedValue({
      data: {
        knowledge_point: { id: 2, name: '栈', subject: '数据结构', parent_id: 1 },
        ready: true,
        threshold: 70,
        items: [],
      },
    } as any)
    vi.mocked(knowledgePointsApi.learningPath).mockResolvedValue({
      data: {
        target: { id: 2, name: '栈', subject: '数据结构', parent_id: 1 },
        ready: true,
        threshold: 70,
        steps: [],
      },
    } as any)
  })

  it('加载并渲染全部知识点字段', async () => {
    const wrapper = await setup()
    expect(knowledgePointsApi.list).toHaveBeenCalledTimes(1)
    expect(bodyRows(wrapper)).toHaveLength(4)

    const row = rowByName(wrapper, '栈')!
    expect(row.text()).toContain('数据结构')
    expect(row.text()).toContain('线性表')
    expect(row.text()).toContain('启用')
    expect(row.text()).toContain('管理员')
    expect(row.text()).toContain('2026-10-01')
  })

  it('展示层级缩进与父级名称', async () => {
    const wrapper = await setup()
    expect(rowByName(wrapper, '栈')!.find('.kp-name').attributes('style')).toContain('18px')
    expect(rowByName(wrapper, '顺序栈')!.find('.kp-name').attributes('style')).toContain('36px')
    const root = rowByName(wrapper, '线性表')!
    expect(root.find('.kp-name').attributes('style')).toBeUndefined()
    expect(root.find('.kp-branch').exists()).toBe(false)
    expect(root.text()).toContain('—')
  })

  it('按 subject 筛选', async () => {
    const wrapper = await setup()
    await wrapper.find('.filter-row select').setValue('操作系统')
    const rows = bodyRows(wrapper)
    expect(rows).toHaveLength(1)
    expect(rows[0].text()).toContain('进程')
  })

  it('按名称搜索', async () => {
    const wrapper = await setup()
    await wrapper.find('.filter-row input').setValue('栈')
    const rows = bodyRows(wrapper)
    expect(rows).toHaveLength(2)
    expect(rows.map((row: any) => row.text()).join()).not.toContain('进程')
  })

  it('无数据时展示空态，筛选无结果时展示另一提示', async () => {
    const empty = await setup([])
    expect(empty.text()).toContain('还没有结构化知识点')

    const wrapper = await setup()
    await wrapper.find('.filter-row input').setValue('不存在')
    expect(wrapper.text()).toContain('没有符合筛选条件的知识点')
  })

  it('加载失败时展示后端错误信息', async () => {
    vi.mocked(knowledgePointsApi.list).mockRejectedValue({
      response: { data: { detail: '登录状态无效或已过期' } },
    })
    const wrapper = mount(AdminKnowledgePointsView) as VueWrapper<any>
    await flushPromises()
    expect(wrapper.text()).toContain('登录状态无效或已过期')
  })

  it('创建知识点：不发送 source，由后端沿用默认规则', async () => {
    const wrapper = await setup()
    vi.mocked(knowledgePointsApi.create).mockResolvedValue({ data: kp(9, '队列') } as any)

    await buttonByText(wrapper, '新增知识点')!.trigger('click')
    await formField(wrapper, 0).find('input').setValue('队列')
    await formField(wrapper, 1).find('input').setValue('数据结构')
    await buttonByText(wrapper, '保存')!.trigger('click')
    await flushPromises()

    expect(knowledgePointsApi.create).toHaveBeenCalledWith({
      name: '队列',
      subject: '数据结构',
      parent_id: null,
      description: null,
      status: 'active',
      node_type: 'concept',
      code: null,
      aliases: null,
      difficulty: null,
      estimated_minutes: null,
    })
    expect(vi.mocked(knowledgePointsApi.create).mock.calls[0][0]).not.toHaveProperty('source')
    expect(knowledgePointsApi.list).toHaveBeenCalledTimes(2)
  })

  it('编辑知识点：回填表单并调用 update', async () => {
    const wrapper = await setup()
    vi.mocked(knowledgePointsApi.update).mockResolvedValue({ data: kp(2, '栈') } as any)

    await rowByName(wrapper, '栈')!.find('[title="编辑"]').trigger('click')
    expect((formField(wrapper, 0).find('input').element as HTMLInputElement).value).toBe('栈')
    expect((formField(wrapper, 1).find('input').element as HTMLInputElement).value).toBe('数据结构')

    await formField(wrapper, 0).find('input').setValue('栈结构')
    await buttonByText(wrapper, '保存')!.trigger('click')
    await flushPromises()

    expect(knowledgePointsApi.update).toHaveBeenCalledWith(2, {
      name: '栈结构',
      subject: '数据结构',
      parent_id: 1,
      description: null,
      status: 'active',
      node_type: 'concept',
      code: null,
      aliases: null,
      difficulty: null,
      estimated_minutes: null,
    })
  })

  it('名称或学科为空时不提交', async () => {
    const wrapper = await setup()
    await buttonByText(wrapper, '新增知识点')!.trigger('click')
    await formField(wrapper, 0).find('input').setValue('只有名称')
    await buttonByText(wrapper, '保存')!.trigger('click')
    await flushPromises()

    expect(knowledgePointsApi.create).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('知识点名称与学科不能为空')
  })

  it('删除成功并刷新列表', async () => {
    const wrapper = await setup()
    vi.mocked(knowledgePointsApi.remove).mockResolvedValue({ data: undefined } as any)

    await rowByName(wrapper, '线性表')!.find('[title="删除"]').trigger('click')
    await flushPromises()

    expect(knowledgePointsApi.remove).toHaveBeenCalledWith(1)
    expect(knowledgePointsApi.list).toHaveBeenCalledTimes(2)
  })

  it('存在子知识点时展示后端中文错误', async () => {
    const wrapper = await setup()
    vi.mocked(knowledgePointsApi.remove).mockRejectedValue({
      response: { data: { detail: '存在子知识点，无法删除' } },
    })

    await rowByName(wrapper, '线性表')!.find('[title="删除"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('存在子知识点，无法删除')
    expect(knowledgePointsApi.list).toHaveBeenCalledTimes(1)
  })

  it('已被题目关联时展示后端中文错误', async () => {
    const wrapper = await setup()
    vi.mocked(knowledgePointsApi.remove).mockRejectedValue({
      response: { data: { detail: '知识点已被题目关联，请先解除关联' } },
    })

    await rowByName(wrapper, '栈')!.find('[title="删除"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('知识点已被题目关联，请先解除关联')
  })

  it('父知识点下拉只显示同学科知识点', async () => {
    const wrapper = await setup()
    await buttonByText(wrapper, '新增知识点')!.trigger('click')
    await formField(wrapper, 1).find('input').setValue('数据结构')

    const options = formField(wrapper, 2)
      .findAll('option')
      .map((option: any) => cleanText(option.text()))
    expect(options).toEqual(['无父级（顶层）', '线性表', '栈', '顺序栈'])
    expect(options).not.toContain('进程')
  })

  it('编辑时父级候选排除自身与后代', async () => {
    const wrapper = await setup()
    await rowByName(wrapper, '栈')!.find('[title="编辑"]').trigger('click')

    const options = formField(wrapper, 2)
      .findAll('option')
      .map((option: any) => cleanText(option.text()))
    expect(options).toEqual(['无父级（顶层）', '线性表'])
  })

  it('学科变更后清空跨学科父级', async () => {
    const wrapper = await setup()
    await rowByName(wrapper, '栈')!.find('[title="编辑"]').trigger('click')
    expect((formField(wrapper, 2).find('select').element as HTMLSelectElement).value).toBe('1')

    await formField(wrapper, 1).find('input').setValue('操作系统')
    await flushPromises()

    expect((formField(wrapper, 2).find('select').element as HTMLSelectElement).value).toBe('')
    const options = formField(wrapper, 2)
      .findAll('option')
      .map((option: any) => cleanText(option.text()))
    expect(options).toEqual(['无父级（顶层）', '进程'])
  })

  it('点击「前置关系」展开前置依赖面板，再次点击收起', async () => {
    const wrapper = await setup()
    expect(wrapper.text()).not.toContain('前置关系表示')

    await rowByName(wrapper, '栈')!.find('[title="前置关系"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('前置关系：栈')
    expect(wrapper.text()).toContain('前置关系表示')
    expect(knowledgePointsApi.prerequisites).toHaveBeenCalledWith(2)
    expect(knowledgePointsApi.learningPath).toHaveBeenCalledWith(2)

    await rowByName(wrapper, '栈')!.find('[title="前置关系"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).not.toContain('前置关系表示')
  })

  it('前置面板与父级层级是两套语义，父级列不受前置关系影响', async () => {
    const wrapper = await setup()
    await rowByName(wrapper, '栈')!.find('[title="前置关系"]').trigger('click')
    await flushPromises()

    // 归属层级（parent_id）仍照常展示，加前置关系不会改动表格里的父级名称。
    const row = rowByName(wrapper, '栈')!
    expect(row.text()).toContain('线性表')
    expect(knowledgePointsApi.update).not.toHaveBeenCalled()
  })

  // ---------------------------------------------- 大阶段 4 M1：内容元数据

  it('新增知识点时一并提交编码、别名、难度与预估时长', async () => {
    const wrapper = await setup()
    vi.mocked(knowledgePointsApi.create).mockResolvedValue({ data: kp(9, '二叉树') } as any)

    await buttonByText(wrapper, '新增知识点')!.trigger('click')
    await formField(wrapper, 0).find('input').setValue('二叉树')
    await formField(wrapper, 1).find('input').setValue('数据结构')
    await formField(wrapper, 5).find('input').setValue('DS.TREE.BST')
    // 中英文逗号混用 + 重复项 + 空格，都应在提交前被规范化。
    await formField(wrapper, 6).find('input').setValue('二叉查找树, BST，二叉查找树， ')
    await formField(wrapper, 7).find('select').setValue('hard')
    await formField(wrapper, 8).find('input').setValue('45')
    await buttonByText(wrapper, '保存')!.trigger('click')
    await flushPromises()

    expect(knowledgePointsApi.create).toHaveBeenCalledWith({
      name: '二叉树',
      subject: '数据结构',
      parent_id: null,
      description: null,
      status: 'active',
      node_type: 'concept',
      code: 'DS.TREE.BST',
      aliases: ['二叉查找树', 'BST'],
      difficulty: 'hard',
      estimated_minutes: 45,
    })
  })

  it('元数据留空时提交 null，而不是空字符串或 0', async () => {
    const wrapper = await setup()
    vi.mocked(knowledgePointsApi.create).mockResolvedValue({ data: kp(9, '队列') } as any)

    await buttonByText(wrapper, '新增知识点')!.trigger('click')
    await formField(wrapper, 0).find('input').setValue('队列')
    await formField(wrapper, 1).find('input').setValue('数据结构')
    await formField(wrapper, 6).find('input').setValue(' , ，')
    await buttonByText(wrapper, '保存')!.trigger('click')
    await flushPromises()

    const payload = vi.mocked(knowledgePointsApi.create).mock.calls[0][0] as any
    expect(payload.code).toBeNull()
    expect(payload.aliases).toBeNull()
    expect(payload.difficulty).toBeNull()
    // 时长留空必须是 null —— 不能变成 0 分钟这种会被写进库的假数据。
    expect(payload.estimated_minutes).toBeNull()
  })

  it('编辑时回填已有元数据，并允许清空', async () => {
    const wrapper = await setup([
      kp(5, '二叉树', {
        code: 'DS.TREE.BST',
        aliases: ['二叉查找树', 'BST'],
        difficulty: 'hard',
        estimated_minutes: 45,
      }),
    ])
    vi.mocked(knowledgePointsApi.update).mockResolvedValue({ data: kp(5, '二叉树') } as any)

    await rowByName(wrapper, '二叉树')!.find('[title="编辑"]').trigger('click')
    expect((formField(wrapper, 5).find('input').element as HTMLInputElement).value).toBe(
      'DS.TREE.BST',
    )
    expect((formField(wrapper, 6).find('input').element as HTMLInputElement).value).toBe(
      '二叉查找树, BST',
    )
    expect((formField(wrapper, 7).find('select').element as HTMLSelectElement).value).toBe('hard')
    expect((formField(wrapper, 8).find('input').element as HTMLInputElement).value).toBe('45')

    await formField(wrapper, 5).find('input').setValue('')
    await formField(wrapper, 7).find('select').setValue('')
    await buttonByText(wrapper, '保存')!.trigger('click')
    await flushPromises()

    const payload = vi.mocked(knowledgePointsApi.update).mock.calls[0][1] as any
    expect(payload.code).toBeNull()
    expect(payload.difficulty).toBeNull()
    // 未改动的字段保持原值。
    expect(payload.aliases).toEqual(['二叉查找树', 'BST'])
    expect(payload.estimated_minutes).toBe(45)
  })

  it('预估时长填非整数时不提交并给出中文提示', async () => {
    const wrapper = await setup()
    await buttonByText(wrapper, '新增知识点')!.trigger('click')
    await formField(wrapper, 0).find('input').setValue('栈')
    await formField(wrapper, 1).find('input').setValue('数据结构')
    await formField(wrapper, 8).find('input').setValue('12.5')
    await buttonByText(wrapper, '保存')!.trigger('click')
    await flushPromises()

    expect(knowledgePointsApi.create).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('预估时长必须是不小于 0 的整数分钟')
  })

  it('表单说明写明了别名的作用与难度的边界', async () => {
    const wrapper = await setup()
    await buttonByText(wrapper, '新增知识点')!.trigger('click')
    expect(wrapper.find('.form-hint').text()).toContain('掌握度会被拆散')
    expect(wrapper.find('.form-hint').text()).toContain('不参与掌握度计算')
  })

  // ---------------------------------------------- P0：节点类型（container/concept）

  it('列表展示类型列并区分目录与知识点', async () => {
    const wrapper = await setup([
      kp(1, '数据结构', { node_type: 'container' }),
      kp(2, '栈', { parent_id: 1, node_type: 'concept' }),
    ])

    expect(wrapper.find('.kp-th').findAll('span').map((el: any) => el.text())).toContain('类型')
    const containerRow = rowByName(wrapper, '数据结构')!
    expect(containerRow.text()).toContain('目录')
    expect(containerRow.classes()).toContain('kp-tr-container')

    const conceptRow = rowByName(wrapper, '栈')!
    expect(conceptRow.text()).toContain('知识点')
    expect(conceptRow.classes()).not.toContain('kp-tr-container')
  })

  it('类型筛选可只看目录或只看知识点', async () => {
    const wrapper = await setup([
      kp(1, '数据结构', { node_type: 'container' }),
      kp(2, '栈', { node_type: 'concept' }),
      kp(3, '队列', { node_type: 'concept' }),
    ])

    // 状态筛选是第三个 field（学科 / 类型 / 名称搜索）。
    await wrapper.findAll('.filter-row select')[1].setValue('container')
    await flushPromises()
    expect(bodyRows(wrapper)).toHaveLength(1)
    expect(rowByName(wrapper, '数据结构')).toBeTruthy()

    await wrapper.findAll('.filter-row select')[1].setValue('concept')
    await flushPromises()
    expect(bodyRows(wrapper)).toHaveLength(2)
    expect(rowByName(wrapper, '数据结构')).toBeFalsy()
  })

  it('新增表单默认提交 concept，切换为目录时展示提示', async () => {
    const wrapper = await setup()
    vi.mocked(knowledgePointsApi.create).mockResolvedValue({ data: kp(9, '数据结构') } as any)
    await buttonByText(wrapper, '新增知识点')!.trigger('click')

    // 类型字段在表单末尾，打开时不应显示目录提示。
    expect(wrapper.find('.container-hint').exists()).toBe(false)

    await formField(wrapper, 0).find('input').setValue('数据结构')
    await formField(wrapper, 1).find('input').setValue('数据结构')
    await formField(wrapper, 9).find('select').setValue('container')
    await flushPromises()

    expect(wrapper.find('.container-hint').text()).toContain('不参与题目关联、掌握度、推荐和前置关系')

    await buttonByText(wrapper, '保存')!.trigger('click')
    await flushPromises()

    const payload = vi.mocked(knowledgePointsApi.create).mock.calls[0][0] as any
    expect(payload.node_type).toBe('container')
  })
})
