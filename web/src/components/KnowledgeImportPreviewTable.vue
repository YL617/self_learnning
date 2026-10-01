<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { DIFFICULTY_LABELS, type KnowledgePointDifficulty } from '@/types'
import type { KnowledgeImportIssue, KnowledgeImportPreview, KnowledgeImportPreviewRow } from '@/types'
import { ACTION_LABELS, issueText, plannedCount } from '@/utils/knowledgeImport'

// 后端 preview 最多返回 200 行；一页 50 行，不做虚拟滚动。
const PAGE_SIZE = 50

const props = defineProps<{ preview: KnowledgeImportPreview }>()

const page = ref(1)
const rows = computed(() => props.preview.rows)
const pageCount = computed(() => Math.max(1, Math.ceil(rows.value.length / PAGE_SIZE)))
const pagedRows = computed(() =>
  rows.value.slice((page.value - 1) * PAGE_SIZE, page.value * PAGE_SIZE),
)

// 换了预览结果就回到第一页，避免停留在越界页码上。
watch(
  () => props.preview,
  () => {
    page.value = 1
  },
)

function count(key: string): number {
  return plannedCount(props.preview.planned, key)
}

function difficultyText(value?: string | null): string {
  return value ? DIFFICULTY_LABELS[value as KnowledgePointDifficulty] : '—'
}

function rowClass(row: KnowledgeImportPreviewRow): string {
  if (row.issues.some((issue) => issue.level === 'error')) return 'is-error'
  if (row.issues.some((issue) => issue.level === 'warning')) return 'is-warning'
  return ''
}

function issueClass(issue: KnowledgeImportIssue): string {
  return issue.level === 'error' ? 'text-danger' : 'imp-warn'
}
</script>

<template>
  <div class="imp-stats">
    <div class="stat-card">
      <span class="stat-label">总行数</span>
      <span class="stat-value">{{ preview.total_rows }}</span>
    </div>
    <div class="stat-card">
      <span class="stat-label">将创建</span>
      <span class="stat-value">{{ count('create') }}</span>
    </div>
    <div class="stat-card">
      <span class="stat-label">将跳过</span>
      <span class="stat-value">{{ count('skip') }}</span>
    </div>
    <div class="stat-card">
      <span class="stat-label">将补空</span>
      <span class="stat-value">{{ count('update_empty') }}</span>
    </div>
    <div class="stat-card">
      <span class="stat-label">自动创建父节点</span>
      <span class="stat-value">{{ count('create_parent') }}</span>
    </div>
    <div class="stat-card">
      <span class="stat-label">错误数</span>
      <span class="stat-value" :class="{ 'is-bad': preview.error_rows }">
        {{ preview.error_rows }}
      </span>
    </div>
    <div class="stat-card">
      <span class="stat-label">警告数</span>
      <span class="stat-value">{{ preview.warning_rows }}</span>
    </div>
  </div>

  <ul v-if="preview.parse_notes.length" class="imp-list imp-notes">
    <li v-for="(note, index) in preview.parse_notes" :key="`n-${index}`">{{ note }}</li>
  </ul>
  <p v-if="preview.truncated" class="muted">
    仅展示前 {{ preview.rows.length }} 行，实际共 {{ preview.total_rows }} 行。
  </p>

  <div class="imp-table">
    <div class="imp-tr imp-th">
      <span>行号</span>
      <span>学科</span>
      <span>层级路径</span>
      <span>名称</span>
      <span>别名</span>
      <span>难度</span>
      <span>预计学时</span>
      <span>编码</span>
      <span>动作</span>
      <span>校验结论</span>
    </div>
    <div v-for="row in pagedRows" :key="row.row" class="imp-tr" :class="rowClass(row)">
      <span class="muted">{{ row.row }}</span>
      <span>{{ row.subject }}</span>
      <span class="muted">{{ row.parent_path || '—' }}</span>
      <span class="imp-name">{{ row.name }}</span>
      <span class="muted">{{ row.aliases?.length ? row.aliases.join(' / ') : '—' }}</span>
      <span class="muted">{{ difficultyText(row.difficulty) }}</span>
      <span class="muted">{{ row.estimated_minutes ?? '—' }}</span>
      <span class="muted">{{ row.code || '—' }}</span>
      <span>
        <span class="badge" :class="row.action === 'create' ? 'badge-green' : 'badge-amber'">
          {{ ACTION_LABELS[row.action] ?? row.action }}
        </span>
      </span>
      <span class="imp-issues">
        <span v-for="(issue, index) in row.issues" :key="`i-${index}`" :class="issueClass(issue)">
          {{ issueText(issue) }}
        </span>
        <span v-if="!row.issues.length" class="muted">—</span>
      </span>
    </div>
  </div>

  <div v-if="pageCount > 1" class="imp-pager">
    <button class="btn btn-ghost" type="button" :disabled="page <= 1" @click="page--">
      上一页
    </button>
    <span class="muted">第 {{ page }} / {{ pageCount }} 页</span>
    <button class="btn btn-ghost" type="button" :disabled="page >= pageCount" @click="page++">
      下一页
    </button>
  </div>
</template>

<style scoped>
.imp-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}

.imp-stats .stat-value.is-bad {
  color: #dc2626;
}

.imp-notes {
  font-size: 12.5px;
  line-height: 1.7;
}

.imp-list {
  margin: 0;
  padding-left: 18px;
  line-height: 1.8;
}

.imp-table {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 12px;
  overflow-x: auto;
}

.imp-tr {
  display: grid;
  grid-template-columns: 0.5fr 1fr 1.4fr 1.2fr 1.4fr 0.7fr 0.8fr 1.2fr 0.7fr 2.4fr;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 13px;
  min-width: 1080px;
}

.imp-tr.is-error {
  background: #fef2f2;
  border-color: #fca5a5;
}

.imp-tr.is-warning {
  background: #fffbeb;
  border-color: #fcd34d;
}

.imp-th {
  background: var(--surface-2);
  font-weight: 700;
  color: var(--text-2);
}

.imp-name {
  font-weight: 600;
  overflow-wrap: anywhere;
}

.imp-issues {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 12.5px;
}

.imp-warn {
  color: #b45309;
}

.imp-pager {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
}

.text-danger {
  color: #dc2626;
}
</style>
