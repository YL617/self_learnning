<script setup lang="ts">
import { Lightbulb, Plus, Route, Trash2 } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'

import { knowledgePointsApi } from '@/api/knowledgePoints'
import type {
  KnowledgePoint,
  LearningPath,
  PrerequisiteDetail,
  PrerequisiteSuggestion,
} from '@/types'

const props = defineProps<{ knowledgePointId: number; knowledgePointName?: string }>()
const emit = defineEmits<{ (e: 'changed'): void }>()

const detail = ref<PrerequisiteDetail | null>(null)
const path = ref<LearningPath | null>(null)
const candidates = ref<KnowledgePoint[]>([])
const suggestions = ref<PrerequisiteSuggestion[]>([])
const suggestionNote = ref('')
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const success = ref('')

const selectedId = ref<number | ''>('')
const strength = ref(100)
const note = ref('')

const available = computed(() =>
  candidates.value.filter(
    (item) =>
      item.id !== props.knowledgePointId &&
      !(detail.value?.items ?? []).some((edge) => edge.prerequisite_id === item.id),
  ),
)

async function load() {
  if (!props.knowledgePointId) return
  loading.value = true
  error.value = ''
  try {
    const [detailRes, pathRes, listRes] = await Promise.all([
      knowledgePointsApi.prerequisites(props.knowledgePointId),
      knowledgePointsApi.learningPath(props.knowledgePointId),
      // P0：前置端点只能是可学习知识点，目录节点不进候选池。
      knowledgePointsApi.list({ node_type: 'concept' }),
    ])
    detail.value = detailRes.data
    path.value = pathRes.data
    candidates.value = listRes.data
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '前置关系加载失败'
  } finally {
    loading.value = false
  }
}

watch(() => props.knowledgePointId, load, { immediate: true })

// P0：后端 NotLearnableNode 会返回「目录节点…」类中文详情，这里补一层更直白的提示。
function describeError(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string' && detail) {
    if (detail.includes('目录节点')) {
      return `${detail}（目录仅用于组织知识结构，不能参与前置关系）`
    }
    return detail
  }
  return fallback
}

async function add() {
  if (selectedId.value === '' || busy.value) return
  busy.value = true
  error.value = ''
  success.value = ''
  try {
    await knowledgePointsApi.addPrerequisite(props.knowledgePointId, {
      prerequisite_id: Number(selectedId.value),
      strength: strength.value,
      note: note.value.trim() || null,
    })
    success.value = '已添加前置关系'
    selectedId.value = ''
    note.value = ''
    await load()
    emit('changed')
  } catch (err: any) {
    error.value = describeError(err, '添加失败：该关系可能已存在或会形成循环')
  } finally {
    busy.value = false
  }
}

async function remove(prerequisiteId: number) {
  busy.value = true
  error.value = ''
  success.value = ''
  try {
    await knowledgePointsApi.removePrerequisite(props.knowledgePointId, prerequisiteId)
    success.value = '已删除前置关系'
    await load()
    emit('changed')
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '删除失败，请稍后重试'
  } finally {
    busy.value = false
  }
}

async function askAi() {
  busy.value = true
  error.value = ''
  success.value = ''
  suggestions.value = []
  suggestionNote.value = ''
  try {
    const { data } = await knowledgePointsApi.suggestPrerequisites(props.knowledgePointId)
    suggestions.value = data.suggestions
    suggestionNote.value = data.note || ''
  } catch (err: any) {
    error.value = describeError(err, 'AI 提议失败，请稍后重试')
  } finally {
    busy.value = false
  }
}

// AI 建议需要管理员显式确认才会落库（LLM 只提议，不写入）。
async function acceptSuggestion(item: PrerequisiteSuggestion) {
  selectedId.value = item.prerequisite_id
  strength.value = 100
  note.value = `AI 建议：${item.reason}`
  await add()
  suggestions.value = suggestions.value.filter((s) => s.prerequisite_id !== item.prerequisite_id)
}
</script>

<template>
  <div class="prereq">
    <p v-if="error" class="text-danger">{{ error }}</p>
    <p v-if="success" class="text-success">{{ success }}</p>

    <div v-if="loading" class="empty">加载中...</div>
    <template v-else-if="detail">
      <div class="prereq-head">
        <strong>前置知识</strong>
        <span class="badge" :class="detail.ready ? 'badge-green' : 'badge-amber'">
          {{ detail.ready ? '前置已满足，可以开始' : '存在未满足的硬前置' }}
        </span>
      </div>
      <p v-if="!detail.items.length" class="empty">暂无前置知识点</p>
      <ul v-else class="prereq-list">
        <li v-for="edge in detail.items" :key="edge.id">
          <span class="prereq-name">{{ edge.prerequisite?.name || `#${edge.prerequisite_id}` }}</span>
          <span class="muted">强度 {{ edge.strength }}</span>
          <span class="badge" :class="edge.satisfied ? 'badge-green' : 'badge-amber'">
            {{ edge.satisfied ? '已满足' : edge.blocking ? '未满足（硬前置）' : '未满足（软前置）' }}
          </span>
          <span v-if="edge.note" class="muted prereq-note">{{ edge.note }}</span>
          <button class="btn btn-ghost" type="button" :disabled="busy" @click="remove(edge.prerequisite_id)">
            <Trash2 :size="14" color="#dc2626" />
          </button>
        </li>
      </ul>

      <div class="prereq-form">
        <select v-model="selectedId" class="select">
          <option value="">选择前置知识点</option>
          <option v-for="item in available" :key="item.id" :value="item.id">
            {{ item.name }}（{{ item.subject }}）
          </option>
        </select>
        <label class="strength-field">
          <span class="muted">强度 {{ strength }}</span>
          <input v-model.number="strength" type="range" min="0" max="100" step="10" />
        </label>
        <input v-model="note" class="input" placeholder="备注（可选）" />
        <button class="btn btn-primary" type="button" :disabled="busy || selectedId === ''" @click="add">
          <Plus :size="15" />
          添加前置
        </button>
        <button class="btn btn-outline" type="button" :disabled="busy" @click="askAi">
          <Lightbulb :size="15" />
          AI 提议
        </button>
      </div>

      <div v-if="suggestions.length || suggestionNote" class="prereq-suggest">
        <p class="muted">
          AI 只提议、不落库；点击「采纳」后才会建立前置关系。
        </p>
        <p v-if="suggestionNote" class="muted">{{ suggestionNote }}</p>
        <ul>
          <li v-for="item in suggestions" :key="item.prerequisite_id">
            <span>{{ item.prerequisite_name }}</span>
            <span class="muted">{{ item.reason }}</span>
            <span class="muted">置信度 {{ item.confidence }}</span>
            <button class="btn btn-outline" type="button" :disabled="busy" @click="acceptSuggestion(item)">
              采纳
            </button>
          </li>
        </ul>
      </div>

      <div v-if="path" class="prereq-path">
        <div class="prereq-head">
          <strong><Route :size="15" /> 学习路径</strong>
          <span class="muted">按前置依赖拓扑排序</span>
        </div>
        <ol>
          <li v-for="step in path.steps" :key="step.knowledge_point.id">
            <span :class="{ 'is-target': step.is_target }">{{ step.knowledge_point.name }}</span>
            <span class="muted">
              {{ step.mastery_score == null ? '暂无掌握度' : `掌握度 ${step.mastery_score}%` }}
            </span>
            <span class="badge" :class="step.satisfied ? 'badge-green' : 'badge-amber'">
              {{ step.is_target ? '目标' : step.satisfied ? '已满足' : '待掌握' }}
            </span>
          </li>
        </ol>
      </div>
    </template>
  </div>
</template>

<style scoped>
.prereq {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.prereq-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.prereq-list,
.prereq-suggest ul,
.prereq-path ol {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.prereq-list li,
.prereq-suggest li,
.prereq-path li {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 13px;
}

.prereq-name {
  font-weight: 600;
}

.prereq-note {
  font-size: 12px;
}

.prereq-form {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  flex-wrap: wrap;
  padding-top: 8px;
  border-top: 1px dashed var(--border);
}

.prereq-form .select,
.prereq-form .input {
  min-width: 180px;
}

.strength-field {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 12px;
}

.prereq-path li .is-target {
  font-weight: 700;
  color: var(--teal);
}

.text-success {
  color: #15803d;
}
</style>
