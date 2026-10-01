<script setup lang="ts">
import { Pencil, Plus, RefreshCw, Route, Search, Trash2, X } from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'

import { knowledgePointsApi, type KnowledgePointPayload } from '@/api/knowledgePoints'
import PrerequisiteEditor from '@/components/PrerequisiteEditor.vue'
import type { KnowledgePoint } from '@/types'
import { buildRows, parentCandidates, statusLabel } from '@/utils/knowledgePoints'

const SOURCE_LABELS: Record<string, string> = {
  system: '系统',
  admin: '管理员',
  ai: 'AI',
}

const items = ref<KnowledgePoint[]>([])
const loading = ref(false)
const error = ref('')
const success = ref('')

const subjectFilter = ref('')
const query = ref('')

const formOpen = ref(false)
const editing = ref<KnowledgePoint | null>(null)
const saving = ref(false)
const formError = ref('')
const form = ref<{
  name: string
  subject: string
  parent_id: number | null
  description: string
  status: 'active' | 'pending' | 'disabled'
}>({
  name: '',
  subject: '',
  parent_id: null,
  description: '',
  status: 'active',
})

// 学科候选项来自已加载数据，供筛选与表单复用。
const subjects = computed(() =>
  Array.from(new Set(items.value.map((item) => item.subject))).sort((a, b) =>
    a.localeCompare(b),
  ),
)

const rows = computed(() =>
  buildRows(items.value, { subject: subjectFilter.value, query: query.value }),
)

const parentOptions = computed(() =>
  parentCandidates(items.value, form.value.subject, editing.value?.id ?? null),
)

async function load() {
  loading.value = true
  try {
    const { data } = await knowledgePointsApi.list()
    items.value = data
    error.value = ''
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '知识点加载失败'
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  formError.value = ''
  form.value = {
    name: '',
    subject: subjectFilter.value || '',
    parent_id: null,
    description: '',
    status: 'active',
  }
  formOpen.value = true
}

function openEdit(item: KnowledgePoint) {
  editing.value = item
  formError.value = ''
  form.value = {
    name: item.name,
    subject: item.subject,
    parent_id: item.parent_id ?? null,
    description: item.description ?? '',
    status: (item.status as 'active' | 'pending' | 'disabled') || 'active',
  }
  formOpen.value = true
}

function closeForm() {
  formOpen.value = false
  editing.value = null
  formError.value = ''
}

// 学科变化后，原先选中的父级可能已跨学科，需清空由前端先行兜底。
function onSubjectChange() {
  if (form.value.parent_id == null) return
  const parent = items.value.find((item) => item.id === form.value.parent_id)
  if (!parent || parent.subject !== form.value.subject) {
    form.value.parent_id = null
  }
}

function onParentChange(event: Event) {
  const raw = (event.target as HTMLSelectElement).value
  form.value.parent_id = raw ? Number(raw) : null
}

async function save() {
  if (!form.value.name.trim() || !form.value.subject.trim()) {
    formError.value = '知识点名称与学科不能为空'
    return
  }
  saving.value = true
  formError.value = ''
  success.value = ''
  const payload: KnowledgePointPayload = {
    name: form.value.name.trim(),
    subject: form.value.subject.trim(),
    parent_id: form.value.parent_id,
    description: form.value.description.trim() || null,
    status: form.value.status,
  }
  try {
    if (editing.value) {
      await knowledgePointsApi.update(editing.value.id, payload)
      success.value = `已更新知识点「${payload.name}」`
    } else {
      await knowledgePointsApi.create(payload)
      success.value = `已创建知识点「${payload.name}」`
    }
    closeForm()
    await load()
  } catch (err: any) {
    formError.value = err?.response?.data?.detail || '保存失败，请稍后重试'
  } finally {
    saving.value = false
  }
}

async function remove(item: KnowledgePoint) {
  if (!window.confirm(`确定删除知识点「${item.name}」吗？此操作不可恢复。`)) return
  error.value = ''
  success.value = ''
  try {
    await knowledgePointsApi.remove(item.id)
    success.value = `已删除知识点「${item.name}」`
    await load()
  } catch (err: any) {
    // 后端业务错误（存在子知识点 / 已被题目关联）原样展示为可读中文。
    error.value = err?.response?.data?.detail || '删除失败，请稍后重试'
  }
}

function clearFilters() {
  subjectFilter.value = ''
  query.value = ''
}

// 大阶段 3：前置依赖 DAG 管理（展开式面板，避免再次改动表格列宽）。
const prerequisiteTarget = ref<KnowledgePoint | null>(null)

function togglePrerequisites(item: KnowledgePoint) {
  prerequisiteTarget.value =
    prerequisiteTarget.value?.id === item.id ? null : item
}

onMounted(load)
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">知识点管理</h1>
        <p class="page-subtitle">维护结构化知识点，供出题与题目关联使用</p>
      </div>
      <div class="row gap">
        <button class="btn btn-outline" type="button" :disabled="loading" @click="load">
          <RefreshCw :size="16" />
          刷新
        </button>
        <button class="btn btn-primary" type="button" @click="openCreate">
          <Plus :size="16" />
          新增知识点
        </button>
      </div>
    </div>

    <p v-if="error" class="text-danger">{{ error }}</p>
    <p v-if="success" class="text-success">{{ success }}</p>

    <div class="card">
      <div class="filter-row">
        <div class="field">
          <span>学科筛选</span>
          <select v-model="subjectFilter" class="select">
            <option value="">全部学科</option>
            <option v-for="subject in subjects" :key="subject" :value="subject">
              {{ subject }}
            </option>
          </select>
        </div>
        <div class="field">
          <span>名称搜索</span>
          <input v-model="query" class="input" placeholder="输入知识点名称" />
        </div>
        <button class="btn btn-ghost" type="button" @click="clearFilters">
          <X :size="16" />
          清除
        </button>
      </div>
      <p class="muted filter-hint">
        <Search :size="13" />
        共 {{ items.length }} 个知识点，当前筛选显示 {{ rows.length }} 个
      </p>
    </div>

    <div v-if="formOpen" class="card">
      <div class="card-head">
        <h2>{{ editing ? '编辑知识点' : '新增知识点' }}</h2>
        <button class="btn btn-ghost" type="button" @click="closeForm">
          <X :size="16" />
          取消
        </button>
      </div>
      <div class="form-grid">
        <div class="field">
          <span>名称</span>
          <input v-model="form.name" class="input" placeholder="例如：栈" />
        </div>
        <div class="field">
          <span>学科</span>
          <input
            v-model="form.subject"
            class="input"
            list="kp-subject-options"
            placeholder="例如：数据结构"
            @input="onSubjectChange"
          />
          <datalist id="kp-subject-options">
            <option v-for="subject in subjects" :key="subject" :value="subject" />
          </datalist>
        </div>
        <div class="field">
          <span>父知识点（可选，仅限同学科）</span>
          <select
            class="select"
            :value="form.parent_id ?? ''"
            :disabled="!form.subject.trim()"
            @change="onParentChange"
          >
            <option value="">无父级（顶层）</option>
            <option v-for="option in parentOptions" :key="option.id" :value="option.id">
              {{ option.name }}
            </option>
          </select>
        </div>
        <div class="field">
          <span>状态</span>
          <select v-model="form.status" class="select">
            <option value="active">启用</option>
            <option value="pending">待审核</option>
            <option value="disabled">停用</option>
          </select>
        </div>
        <div class="field field-wide">
          <span>描述（可选）</span>
          <input v-model="form.description" class="input" placeholder="补充说明" />
        </div>
      </div>
      <p v-if="formError" class="text-danger">{{ formError }}</p>
      <div class="row gap" style="margin-top: 12px">
        <button class="btn btn-primary" type="button" :disabled="saving" @click="save">
          {{ saving ? '保存中...' : '保存' }}
        </button>
        <button class="btn btn-ghost" type="button" @click="closeForm">取消</button>
      </div>
    </div>

    <div v-if="loading && !items.length" class="empty">加载中...</div>
    <div v-else-if="!rows.length" class="empty">
      {{
        items.length
          ? '没有符合筛选条件的知识点'
          : '还没有结构化知识点，点击「新增知识点」创建第一个'
      }}
    </div>
    <div v-else class="kp-table">
      <div class="kp-tr kp-th">
        <span>名称</span>
        <span>学科</span>
        <span>父知识点</span>
        <span>状态</span>
        <span>来源</span>
        <span>创建时间</span>
        <span>操作</span>
      </div>
      <div v-for="row in rows" :key="row.id" class="kp-tr">
        <span
          class="kp-name"
          :style="row.depth ? { paddingLeft: `${row.depth * 18}px` } : undefined"
        >
          <span v-if="row.depth" class="kp-branch">└</span>{{ row.name }}
        </span>
        <span><span class="badge">{{ row.subject }}</span></span>
        <span class="muted">{{ row.parentName || '—' }}</span>
        <span
          class="badge"
          :class="row.status === 'active' ? 'badge-green' : 'badge-amber'"
        >
          {{ statusLabel(row.status) }}
        </span>
        <span class="muted">{{ SOURCE_LABELS[row.source] || row.source }}</span>
        <span class="muted">{{ (row.created_at || '').slice(0, 10) }}</span>
        <span class="row gap">
          <button class="btn btn-ghost" type="button" title="编辑" @click="openEdit(row)">
            <Pencil :size="15" />
          </button>
          <button
            class="btn btn-ghost"
            type="button"
            title="前置关系"
            @click="togglePrerequisites(row)"
          >
            <Route :size="15" />
          </button>
          <button class="btn btn-ghost" type="button" title="删除" @click="remove(row)">
            <Trash2 :size="15" color="#dc2626" />
          </button>
        </span>
      </div>
    </div>

    <div v-if="prerequisiteTarget" class="card">
      <div class="card-head">
        <h2>前置关系：{{ prerequisiteTarget.name }}</h2>
        <button class="btn btn-ghost" type="button" @click="prerequisiteTarget = null">
          <X :size="16" />
          收起
        </button>
      </div>
      <p class="muted" style="margin-top: 0">
        前置关系表示「必须先学」，与父知识点的归属层级不同；多个前置会组成学习路径。
      </p>
      <PrerequisiteEditor
        :knowledge-point-id="prerequisiteTarget.id"
        :knowledge-point-name="prerequisiteTarget.name"
      />
    </div>
  </section>
</template>

<style scoped>
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 14px;
}

.card-head h2 {
  margin: 0;
}

.filter-row {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  flex-wrap: wrap;
}

.filter-row .field {
  min-width: 200px;
}

.filter-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 12px 0 0;
  font-size: 12.5px;
}

.field-wide {
  grid-column: 1 / -1;
}

.text-success {
  color: #15803d;
}

.kp-table {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.kp-tr {
  display: grid;
  grid-template-columns: 2.2fr 1fr 1.4fr 0.8fr 0.8fr 1fr 0.9fr;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 13.5px;
}

.kp-th {
  background: var(--surface-2);
  font-weight: 700;
  color: var(--text-2);
  font-size: 12.5px;
}

.kp-name {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  min-width: 0;
  overflow-wrap: anywhere;
}

.kp-branch {
  color: var(--text-2);
}

@media (max-width: 900px) {
  .kp-tr {
    grid-template-columns: 1fr 1fr;
  }

  .kp-th {
    display: none;
  }
}
</style>
