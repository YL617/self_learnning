<script setup lang="ts">
import { CheckCircle2, Download } from 'lucide-vue-next'

import type { KnowledgeImportApplyResult, KnowledgeImportPreviewRow } from '@/types'
import { downloadBlob, toCsvBlob } from '@/utils/csvExport'
import { ACTION_LABELS, STATUS_LABELS, issueText } from '@/utils/knowledgeImport'

const props = defineProps<{
  result: KnowledgeImportApplyResult
  fallbackRows?: KnowledgeImportPreviewRow[]
}>()

// apply 成功时后端会回传逐行结果；兼容它为空的情况（用预览行兜底）。
function resultRows(): KnowledgeImportPreviewRow[] {
  return props.result.rows.length ? props.result.rows : (props.fallbackRows ?? [])
}

// 结果 CSV 完全在浏览器本地生成（服务端不落盘），并做公式注入防护。
function exportCsv() {
  const table: unknown[][] = [
    ['行号', '学科', '层级路径', '名称', '类型', '类型来源', '别名', '难度', '预计学时', '编码', '动作', '校验结论'],
    ...resultRows().map((row) => [
      row.row,
      row.subject,
      row.parent_path ?? '',
      row.name,
      row.node_type === 'container' ? '目录' : '知识点',
      row.node_type_source ?? '',
      (row.aliases ?? []).join('|'),
      row.difficulty ?? '',
      row.estimated_minutes ?? '',
      row.code ?? '',
      ACTION_LABELS[row.action] ?? row.action,
      row.issues.map((issue) => issueText(issue)).join('; '),
    ]),
  ]
  downloadBlob(toCsvBlob(table), `knowledge-import-${props.result.batch_id}.csv`)
}
</script>

<template>
  <div class="card">
    <div class="card-head">
      <h2>
        <CheckCircle2 :size="18" />
        3. 导入完成（批次 #{{ result.batch_id }}）
      </h2>
      <button class="btn btn-outline" type="button" @click="exportCsv">
        <Download :size="15" />
        下载本批结果 CSV
      </button>
    </div>
    <div class="imp-stats">
      <div class="stat-card">
        <span class="stat-label">状态</span>
        <span class="stat-value">{{ STATUS_LABELS[result.status] ?? result.status }}</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">新增知识点</span>
        <span class="stat-value">{{ result.created_concept_count }}</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">新增目录</span>
        <span class="stat-value">{{ result.created_container_count }}</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">补空</span>
        <span class="stat-value">{{ result.updated_count }}</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">跳过</span>
        <span class="stat-value">{{ result.skipped_count }}</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">耗时</span>
        <span class="stat-value">{{ result.duration_ms }} ms</span>
      </div>
    </div>
    <p class="muted">批次审计与回滚可在「批次历史」标签页中查看。</p>
  </div>
</template>

<style scoped>
.card-head h2 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
}

.imp-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}
</style>
