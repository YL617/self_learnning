<script setup lang="ts">
import { RotateCcw } from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'

import { importErrorMessage, knowledgeImportApi } from '@/api/knowledgeImport'
import type { KnowledgeImportBatch, KnowledgeImportBatchDetail } from '@/types'
import { BLOCKING_LABELS, STATUS_LABELS, STRATEGY_LABELS, formatTime } from '@/utils/knowledgeImport'

const BATCH_LIMIT = 50

const batches = ref<KnowledgeImportBatch[]>([])
const loading = ref(false)
const listError = ref('')
const detail = ref<KnowledgeImportBatchDetail | null>(null)
const detailLoading = ref(false)
const rollbackBusy = ref(false)
const notice = ref('')

const blocked = computed(() => (detail.value?.blocking_references ?? []).length > 0)

async function reload() {
  loading.value = true
  try {
    const { data } = await knowledgeImportApi.batches({ limit: BATCH_LIMIT })
    batches.value = data
    listError.value = ''
  } catch (err) {
    listError.value = importErrorMessage(err, '批次列表加载失败')
  } finally {
    loading.value = false
  }
}

async function openDetail(batch: KnowledgeImportBatch) {
  detailLoading.value = true
  notice.value = ''
  try {
    const { data } = await knowledgeImportApi.batch(batch.id)
    detail.value = data
  } catch (err) {
    listError.value = importErrorMessage(err, '批次详情加载失败')
  } finally {
    detailLoading.value = false
  }
}

async function rollback() {
  const current = detail.value
  if (!current || blocked.value) return

  const lines = [
    `即将回滚批次 #${current.id}：删除本批新建的 ${current.created_count} 个知识点`,
    `（含自动创建父节点 ${current.auto_parent_count} 个；被跳过的 ${current.skipped_count} 条不涉及）。`,
  ]
  if (current.updated_count > 0) {
    lines.push(
      '',
      '注意：本次通过 update_empty 补充的字段不会被还原为空值。',
      '这是已知的设计局限（批次表不保存字段级快照），回滚并非完全可逆。',
    )
  }
  lines.push('', '是否确认？')
  if (!window.confirm(lines.join('\n'))) return

  rollbackBusy.value = true
  notice.value = ''
  try {
    const { data } = await knowledgeImportApi.rollback(current.id)
    const message =
      `已回滚批次 #${data.batch_id}，删除 ${data.deleted_count} 个知识点；` +
      `${data.kept_updated_count} 条补空字段保留原值（不会清空）。`
    await reload()
    // openDetail 会清空上一次的提示，所以刷新完详情后再回填结果。
    await openDetail({ ...current, status: data.status })
    notice.value = message
  } catch (err) {
    notice.value = importErrorMessage(err, '回滚失败')
  } finally {
    rollbackBusy.value = false
  }
}

onMounted(reload)

defineExpose({ reload })
</script>

<template>
  <div class="card">
    <div class="card-head">
      <h2>批次历史</h2>
      <button class="btn btn-outline" type="button" :disabled="loading" @click="reload">刷新</button>
    </div>
    <p v-if="listError" class="text-danger">{{ listError }}</p>
    <div v-if="!batches.length" class="empty">
      {{ loading ? '加载中...' : '还没有导入批次' }}
    </div>
    <div v-else class="imp-table">
      <div class="imp-tr imp-th imp-tr-batch">
        <span>时间</span>
        <span>操作人</span>
        <span>来源</span>
        <span>格式</span>
        <span>策略</span>
        <span>总行数</span>
        <span>新增</span>
        <span>更新</span>
        <span>跳过</span>
        <span>失败</span>
        <span>父节点</span>
        <span>状态</span>
        <span>操作</span>
      </div>
      <div v-for="batch in batches" :key="batch.id" class="imp-tr imp-tr-batch">
        <span class="muted">{{ formatTime(batch.created_at) }}</span>
        <span class="muted">#{{ batch.user_id ?? '—' }}</span>
        <span class="imp-name">{{ batch.source_name || '—' }}</span>
        <span class="muted">{{ batch.source_format }}</span>
        <span class="muted">
          {{ STRATEGY_LABELS[batch.conflict_strategy] ?? batch.conflict_strategy }}
        </span>
        <span class="muted">{{ batch.total_rows }}</span>
        <span>{{ batch.created_count }}</span>
        <span>{{ batch.updated_count }}</span>
        <span>{{ batch.skipped_count }}</span>
        <span :class="{ 'text-danger': batch.failed_count }">{{ batch.failed_count }}</span>
        <span class="muted">{{ batch.auto_parent_count }}</span>
        <span>
          <span class="badge" :class="batch.status === 'applied' ? 'badge-green' : 'badge-amber'">
            {{ STATUS_LABELS[batch.status] ?? batch.status }}
          </span>
        </span>
        <span class="row gap">
          <button class="btn btn-ghost" type="button" @click="openDetail(batch)">查看详情</button>
        </span>
      </div>
    </div>
  </div>

  <div v-if="detail" class="card">
    <div class="card-head">
      <h2>批次 #{{ detail.id }} 详情</h2>
      <div class="row gap">
        <button
          class="btn btn-danger"
          type="button"
          :disabled="detail.status !== 'applied' || blocked || rollbackBusy"
          @click="rollback"
        >
          <RotateCcw :size="15" />
          {{ rollbackBusy ? '回滚中...' : '回滚本批' }}
        </button>
        <button class="btn btn-ghost" type="button" @click="detail = null">收起</button>
      </div>
    </div>

    <p class="muted">
      {{ formatTime(detail.created_at) }} · {{ detail.source_name || '—' }} ·
      {{ STRATEGY_LABELS[detail.conflict_strategy] ?? detail.conflict_strategy }} · 新增
      {{ detail.created_count }} / 补空 {{ detail.updated_count }} / 跳过
      {{ detail.skipped_count }} / 失败 {{ detail.failed_count }}
    </p>
    <p v-if="detail.error_summary" class="text-danger">{{ detail.error_summary }}</p>

    <ul v-if="detail.notes.length" class="imp-list imp-notes">
      <li v-for="(note, index) in detail.notes" :key="`dn-${index}`">{{ note }}</li>
    </ul>

    <div v-if="blocked" class="imp-block imp-blocked">
      <h3 class="text-danger">无法回滚</h3>
      <p class="muted">
        以下知识点已被本批之外的数据引用，删除会破坏完整性。请先解除引用再重试。
      </p>
      <ul class="imp-list">
        <li
          v-for="ref in detail.blocking_references"
          :key="`${ref.knowledge_point_id}-${ref.reason}`"
        >
          <strong>{{ ref.knowledge_point_name }}</strong>
          <span class="badge badge-amber">{{ BLOCKING_LABELS[ref.reason] ?? ref.reason }}</span>
          {{ ref.detail }}
        </li>
      </ul>
    </div>
    <p v-else-if="detail.status === 'applied'" class="muted">
      未检测到外部引用，可以安全回滚（仅删除本批新建的知识点）。
    </p>

    <div class="imp-block">
      <h3>本批知识点（{{ detail.knowledge_points.length }}）</h3>
      <div v-if="!detail.knowledge_points.length" class="muted">本批没有新建知识点。</div>
      <div v-else class="imp-list imp-kps">
        <span v-for="item in detail.knowledge_points" :key="item.id" class="badge">
          {{ item.subject }} / {{ item.name }}
        </span>
      </div>
    </div>

    <p v-if="notice" class="text-success">{{ notice }}</p>
    <p v-if="detailLoading" class="muted">加载中...</p>
  </div>
</template>

<style scoped>
.card-head h2 {
  margin: 0;
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
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 13px;
}

.imp-tr-batch {
  grid-template-columns: 1.2fr 0.7fr 1.6fr 0.7fr 1fr 0.7fr 0.6fr 0.6fr 0.6fr 0.6fr 0.7fr 0.9fr 0.9fr;
  min-width: 1180px;
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

.imp-block {
  margin-top: 12px;
}

.imp-block h3 {
  margin: 0 0 6px;
  font-size: 13.5px;
}

.imp-blocked {
  border-left: 3px solid #dc2626;
  padding-left: 10px;
}

.imp-list {
  margin: 0;
  padding-left: 18px;
  line-height: 1.8;
}

.imp-notes {
  font-size: 12.5px;
  line-height: 1.7;
}

.imp-kps {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding-left: 0;
  list-style: none;
}

.text-danger {
  color: #dc2626;
}
</style>
