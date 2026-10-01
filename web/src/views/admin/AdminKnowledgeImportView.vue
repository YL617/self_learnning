<script setup lang="ts">
import { AlertTriangle, CheckCircle2, Download, FileSpreadsheet, History, Upload, UploadCloud, X } from 'lucide-vue-next'
import { computed, ref } from 'vue'

import {
  importErrorMessage,
  knowledgeImportApi,
  readImportRejection,
  type KnowledgeImportRequest,
} from '@/api/knowledgeImport'
import KnowledgeImportBatchPanel from '@/components/KnowledgeImportBatchPanel.vue'
import KnowledgeImportPreviewTable from '@/components/KnowledgeImportPreviewTable.vue'
import KnowledgeImportResultPanel from '@/components/KnowledgeImportResultPanel.vue'
import type {
  KnowledgeImportApplyResult,
  KnowledgeImportConflictStrategy,
  KnowledgeImportPreview,
  KnowledgeImportRejection,
} from '@/types'
import { downloadBlob } from '@/utils/csvExport'
import { plannedCount, issueText } from '@/utils/knowledgeImport'

const ACCEPT = '.csv,.tsv,.xlsx'

const tab = ref<'import' | 'history'>('import')

const conflictStrategy = ref<KnowledgeImportConflictStrategy>('skip')
const selectedFile = ref<File | null>(null)
const pasteContent = ref('')
const fileInput = ref<HTMLInputElement | null>(null)
const dragging = ref(false)

const previewing = ref(false)
const applying = ref(false)
const preview = ref<KnowledgeImportPreview | null>(null)
const rejection = ref<KnowledgeImportRejection | null>(null)
const importError = ref('')
const applyResult = ref<KnowledgeImportApplyResult | null>(null)

const hasInput = computed(() => Boolean(selectedFile.value) || pasteContent.value.trim() !== '')
const planned = computed(() => preview.value?.planned)

function count(key: string): number {
  return plannedCount(planned.value, key)
}

function onPickFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) selectFile(file)
  input.value = ''
}

function selectFile(file: File) {
  selectedFile.value = file
  // 两条入口互斥：服务端同时收到 file 与 content 会直接 400。
  pasteContent.value = ''
  resetPreview()
}

function onDrop(event: DragEvent) {
  dragging.value = false
  const file = event.dataTransfer?.files?.[0]
  if (!file) return
  if (!/\.(csv|tsv|xlsx)$/i.test(file.name)) {
    importError.value = '只支持 .csv / .tsv / .xlsx 文件；旧版 .xls 请先另存为 .xlsx'
    return
  }
  selectFile(file)
}

function clearFile() {
  selectedFile.value = null
  if (fileInput.value) fileInput.value.value = ''
}

function onPasteInput() {
  if (pasteContent.value) clearFile()
}

function resetPreview() {
  preview.value = null
  rejection.value = null
  importError.value = ''
  applyResult.value = null
}

function buildRequest(): KnowledgeImportRequest {
  return {
    file: selectedFile.value,
    content: selectedFile.value ? null : pasteContent.value,
    conflict_strategy: conflictStrategy.value,
    source_name: selectedFile.value
      ? `文件导入 / ${selectedFile.value.name}`
      : '粘贴导入 / 管理后台',
  }
}

async function runPreview() {
  if (!hasInput.value) return
  previewing.value = true
  resetPreview()
  try {
    const { data } = await knowledgeImportApi.preview(buildRequest())
    preview.value = data
    if (!data.can_apply) {
      importError.value = '存在校验错误，请先修正数据后重新预览'
    }
  } catch (err) {
    rejection.value = readImportRejection(err)
    importError.value = importErrorMessage(err, '预览失败，请检查数据格式后重试')
  } finally {
    previewing.value = false
  }
}

async function runApply() {
  const current = preview.value
  if (!current || !current.can_apply) return

  const lines = [
    '即将执行导入：',
    '',
    `新增 ${count('create')}`,
    `跳过 ${count('skip')}`,
    `补空 ${count('update_empty')}`,
    `自动创建父节点 ${count('create_parent')}`,
    '',
  ]
  if (current.truncated) {
    lines.push(`（预览仅展示前 ${current.rows.length} 行，实际共 ${current.total_rows} 行）`, '')
  }
  lines.push('是否确认？')
  if (!window.confirm(lines.join('\n'))) return

  applying.value = true
  importError.value = ''
  try {
    const { data } = await knowledgeImportApi.apply({
      ...buildRequest(),
      // 乐观锁：preview 之后若数据变了，服务端会 409 而不是执行非本意内容。
      expected_total_rows: current.total_rows,
    })
    applyResult.value = data
  } catch (err) {
    rejection.value = readImportRejection(err)
    importError.value = importErrorMessage(err, '导入失败，数据未发生任何变更')
  } finally {
    applying.value = false
  }
}

async function downloadTemplate() {
  importError.value = ''
  try {
    // 模板接口同样需要管理员鉴权，必须走 axios 才能带上 token。
    const { data } = await knowledgeImportApi.downloadTemplate()
    downloadBlob(data as unknown as Blob, 'knowledge_points_template.csv')
  } catch (err) {
    importError.value = importErrorMessage(err, '模板下载失败')
  }
}
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">知识库导入</h1>
        <p class="page-subtitle">批量导入知识点（CSV / TSV / XLSX / 粘贴），支持预览与批次回滚</p>
      </div>
    </div>

    <div class="segmented imp-tabs">
      <button
        class="btn btn-ghost"
        :class="{ active: tab === 'import' }"
        type="button"
        @click="tab = 'import'"
      >
        <UploadCloud :size="15" />
        导入
      </button>
      <button
        class="btn btn-ghost"
        :class="{ active: tab === 'history' }"
        type="button"
        @click="tab = 'history'"
      >
        <History :size="15" />
        批次历史
      </button>
    </div>

    <template v-if="tab === 'import'">
      <div class="card">
        <div class="card-head">
          <h2>1. 选择数据</h2>
          <button class="btn btn-outline" type="button" @click="downloadTemplate">
            <Download :size="15" />
            下载模板
          </button>
        </div>

        <div class="imp-grid">
          <div
            class="imp-drop"
            :class="{ dragging }"
            @click="fileInput?.click()"
            @dragover.prevent="dragging = true"
            @dragleave.prevent="dragging = false"
            @drop.prevent="onDrop"
          >
            <FileSpreadsheet :size="26" />
            <p class="imp-drop-title">
              {{ selectedFile ? selectedFile.name : '点击或拖拽上传 CSV / TSV / XLSX' }}
            </p>
            <p class="muted imp-drop-hint">单个文件不超过 2 MiB，数据行不超过 500 行</p>
            <input
              ref="fileInput"
              class="imp-file-input"
              type="file"
              :accept="ACCEPT"
              @change="onPickFile"
            />
          </div>

          <div class="imp-or">或</div>

          <div class="field">
            <span>粘贴 Excel / TSV / CSV 内容（含表头）</span>
            <textarea
              v-model="pasteContent"
              class="textarea imp-paste"
              rows="6"
              placeholder="学科&#9;层级路径&#9;知识点名&#9;别名&#9;难度&#9;预计学时&#9;编码"
              @input="onPasteInput"
            />
          </div>
        </div>

        <div class="imp-actions">
          <div class="field imp-strategy">
            <span>冲突策略</span>
            <select v-model="conflictStrategy" class="select">
              <option value="skip">跳过既有知识点（默认）</option>
              <option value="update_empty">仅补齐既有知识点的空字段</option>
            </select>
          </div>
          <button
            class="btn btn-primary"
            type="button"
            :disabled="!hasInput || previewing"
            @click="runPreview"
          >
            <Upload :size="15" />
            {{ previewing ? '预览中...' : '预览' }}
          </button>
          <button v-if="selectedFile" class="btn btn-ghost" type="button" @click="clearFile">
            <X :size="15" />
            移除文件
          </button>
        </div>
        <p class="muted imp-hint">
          导入不会覆盖既有知识点的非空字段；不提供 overwrite 策略。难度只用于展示与推荐，不参与掌握度计算。
        </p>
      </div>

      <p v-if="importError" class="text-danger imp-error">
        <AlertTriangle :size="15" />
        {{ importError }}
      </p>

      <div v-if="rejection" class="card imp-reject">
        <div class="card-head">
          <h2>
            校验未通过
            <span v-if="rejection.code" class="badge badge-amber">{{ rejection.code }}</span>
          </h2>
        </div>
        <div v-if="rejection.batch_errors.length" class="imp-block">
          <h3>整批级问题</h3>
          <ul class="imp-list">
            <li v-for="(issue, index) in rejection.batch_errors" :key="`b-${index}`">
              {{ issueText(issue) }}
            </li>
          </ul>
        </div>
        <div v-if="rejection.cycle.length" class="imp-block">
          <h3>检测到层级成环</h3>
          <p class="imp-cycle">{{ rejection.cycle.join(' → ') }}</p>
          <p class="muted">环上的节点互为祖先，无法确定层级。请打破其中任意一条「层级路径」。</p>
        </div>
        <div v-if="rejection.row_issues.length" class="imp-block">
          <h3>行级问题（共 {{ rejection.row_issues.length }} 条）</h3>
          <ul class="imp-list">
            <li v-for="(issue, index) in rejection.row_issues" :key="`r-${index}`">
              第 {{ issue.row }} 行：{{ issueText(issue) }}
            </li>
          </ul>
        </div>
      </div>

      <div v-if="preview" class="card">
        <div class="card-head">
          <h2>2. 预览结果</h2>
          <div class="row gap">
            <span class="badge">{{ preview.source_format }}</span>
            <span v-if="preview.detected_encoding" class="badge">
              {{ preview.detected_encoding }}
            </span>
            <button
              class="btn btn-primary"
              type="button"
              :disabled="!preview.can_apply || applying"
              @click="runApply"
            >
              <CheckCircle2 :size="15" />
              {{ applying ? '导入中...' : '执行导入' }}
            </button>
          </div>
        </div>
        <p v-if="!preview.can_apply" class="text-danger imp-error">
          <AlertTriangle :size="15" />
          存在 {{ preview.error_rows }} 行校验错误，必须修正后重新预览才能执行导入。
        </p>
        <KnowledgeImportPreviewTable :preview="preview" />
      </div>

      <KnowledgeImportResultPanel
        v-if="applyResult"
        :result="applyResult"
        :fallback-rows="preview?.rows ?? []"
      />
    </template>

    <KnowledgeImportBatchPanel v-else />
  </section>
</template>

<style scoped>
.imp-tabs {
  margin-bottom: 16px;
}

.imp-tabs .btn.active {
  background: var(--surface-2);
  border-color: var(--border);
}

.card-head h2 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
}

.imp-grid {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 14px;
  align-items: center;
}

.imp-drop {
  border: 1px dashed var(--border);
  border-radius: var(--radius-sm);
  padding: 22px 14px;
  text-align: center;
  cursor: pointer;
  color: var(--text-2);
}

.imp-drop.dragging,
.imp-drop:hover {
  border-color: var(--accent);
}

.imp-drop-title {
  margin: 8px 0 4px;
  font-weight: 600;
  color: var(--text-1);
  overflow-wrap: anywhere;
}

.imp-drop-hint {
  margin: 0;
  font-size: 12.5px;
}

.imp-file-input {
  display: none;
}

.imp-or {
  color: var(--text-2);
  font-size: 12.5px;
}

.imp-paste {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12.5px;
}

.imp-actions {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  margin-top: 14px;
  flex-wrap: wrap;
}

.imp-strategy {
  min-width: 240px;
}

.imp-hint {
  font-size: 12.5px;
  line-height: 1.7;
}

.imp-error {
  display: flex;
  align-items: center;
  gap: 6px;
}

.imp-reject {
  border-color: #fca5a5;
}

.imp-block {
  margin-top: 12px;
}

.imp-block h3 {
  margin: 0 0 6px;
  font-size: 13.5px;
}

.imp-cycle {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  background: var(--surface-2);
  border-radius: var(--radius-sm);
  padding: 8px 10px;
  margin: 0 0 6px;
  overflow-wrap: anywhere;
}

.imp-list {
  margin: 0;
  padding-left: 18px;
  line-height: 1.8;
}

.text-danger {
  color: #dc2626;
}
</style>
