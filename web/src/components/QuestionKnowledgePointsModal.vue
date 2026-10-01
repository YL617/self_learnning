<script setup lang="ts">
import { Crown, Plus, Trash2, X } from 'lucide-vue-next'
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import { knowledgePointsApi, toKnowledgePointNameMap } from '@/api/knowledgePoints'
import { questionsApi } from '@/api/questions'
import KnowledgePointSelector from '@/components/KnowledgePointSelector.vue'
import type { KnowledgePoint, Question, QuestionKnowledgePoint } from '@/types'

const props = defineProps<{
  open: boolean
  question: Question | null
}>()

const emit = defineEmits<{
  close: []
  updated: [questionId: number, associations: QuestionKnowledgePoint[]]
}>()

const associations = ref<QuestionKnowledgePoint[]>([])
const kpNameById = ref<Record<number, string>>({})
const selectedId = ref<number | null>(null)
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')

const attachedIds = computed(() => associations.value.map((item) => item.knowledge_point_id))
const hasPrimary = computed(() => associations.value.some((item) => item.role === 'primary'))
const sortedAssociations = computed(() =>
  [...associations.value].sort((a, b) => {
    if (a.role === b.role) return a.id - b.id
    return a.role === 'primary' ? -1 : 1
  }),
)

function nameOf(knowledgePointId: number): string {
  return kpNameById.value[knowledgePointId] ?? `知识点 #${knowledgePointId}`
}

function messageFromError(err: any, fallback: string): string {
  const status = err?.response?.status
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string' && detail) return detail
  if (status === 404) return '题目或知识点不存在'
  if (status === 401) return '登录已过期，请重新登录'
  if (!status) return '网络错误，请稍后重试'
  return fallback
}

async function loadNames(subject: string) {
  try {
    const { data } = await knowledgePointsApi.list({ subject })
    kpNameById.value = { ...kpNameById.value, ...toKnowledgePointNameMap(data) }
  } catch {
    // 名称解析失败不阻塞主流程，关联列表仍可展示 id。
  }
}

async function load() {
  const question = props.question
  if (!question) return
  loading.value = true
  error.value = ''
  notice.value = ''
  selectedId.value = null
  try {
    const { data } = await questionsApi.getQuestionKnowledgePoints(question.id)
    associations.value = data
    emit('updated', question.id, data)
    await loadNames(question.subject)
  } catch (err: any) {
    error.value = messageFromError(err, '加载知识点关联失败')
  } finally {
    loading.value = false
  }
}

async function addAssociation() {
  const question = props.question
  if (!question || selectedId.value === null || busy.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await questionsApi.attachQuestionKnowledgePoint(question.id, {
      knowledge_point_id: selectedId.value,
      role: hasPrimary.value ? 'secondary' : 'primary',
    })
    selectedId.value = null
    await load()
    notice.value = '已添加知识点'
  } catch (err: any) {
    error.value = messageFromError(err, '添加知识点失败')
  } finally {
    busy.value = false
  }
}

async function setPrimary(item: QuestionKnowledgePoint) {
  const question = props.question
  if (!question || busy.value || item.role === 'primary') return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await questionsApi.setPrimaryKnowledgePoint(question.id, item.knowledge_point_id)
    await load()
    notice.value = '已设为主知识点'
  } catch (err: any) {
    error.value = messageFromError(err, '设置主知识点失败')
  } finally {
    busy.value = false
  }
}

async function detach(item: QuestionKnowledgePoint) {
  const question = props.question
  if (!question || busy.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await questionsApi.detachQuestionKnowledgePoint(question.id, item.knowledge_point_id)
    await load()
    notice.value = '已移除关联'
  } catch (err: any) {
    error.value = messageFromError(err, '移除关联失败')
  } finally {
    busy.value = false
  }
}

function close() {
  emit('close')
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') close()
}

watch(
  () => props.open,
  (open) => {
    if (open) {
      load()
      window.addEventListener('keydown', onKeydown)
    } else {
      window.removeEventListener('keydown', onKeydown)
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <Teleport to="body">
    <div v-if="open && question" class="kp-modal-overlay" @click.self="close">
      <div class="kp-modal">
        <div class="kp-modal-head">
          <div>
            <h2>题目知识点</h2>
            <p class="muted kp-subject">{{ question.subject }}</p>
          </div>
          <button class="btn btn-ghost" type="button" title="关闭" @click="close">
            <X :size="16" />
          </button>
        </div>

        <p v-if="error" class="text-danger">{{ error }}</p>
        <p v-else-if="notice" class="text-success">{{ notice }}</p>

        <div class="kp-section">
          <h3>当前关联</h3>
          <p v-if="loading" class="muted">加载中...</p>
          <p v-else-if="!sortedAssociations.length" class="muted">暂无关联知识点</p>
          <ul v-else class="kp-list">
            <li v-for="item in sortedAssociations" :key="item.id" class="kp-item">
              <span class="kp-name">
                <span v-if="item.role === 'primary'" class="badge kp-badge-primary">[主]</span>
                {{ nameOf(item.knowledge_point_id) }}
              </span>
              <span class="kp-actions">
                <button
                  v-if="item.role !== 'primary'"
                  class="btn btn-ghost"
                  type="button"
                  :disabled="busy"
                  @click="setPrimary(item)"
                >
                  <Crown :size="14" />
                  设为主
                </button>
                <button
                  class="btn btn-ghost"
                  type="button"
                  :disabled="busy"
                  title="移除关联"
                  @click="detach(item)"
                >
                  <Trash2 :size="14" color="#dc2626" />
                </button>
              </span>
            </li>
          </ul>
        </div>

        <div class="kp-section">
          <h3>添加知识点</h3>
          <div class="kp-add">
            <KnowledgePointSelector
              v-model="selectedId"
              :subject="question.subject"
              :exclude-ids="attachedIds"
              :disabled="busy"
            />
            <button
              class="btn btn-primary"
              type="button"
              :disabled="busy || selectedId === null"
              @click="addAssociation"
            >
              <Plus :size="16" />
              添加
            </button>
          </div>
          <p class="muted kp-tip">
            第一个知识点默认为主知识点，后续添加默认为次知识点；主知识点每道题最多一个。
          </p>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.kp-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(24, 24, 22, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  z-index: 60;
}

.kp-modal {
  width: 100%;
  max-width: 460px;
  max-height: 86vh;
  overflow-y: auto;
  background: var(--surface, #fffdf8);
  border: 1px solid var(--border, #e7e2d6);
  border-radius: 14px;
  padding: 18px 20px 22px;
  box-shadow: 0 18px 48px rgba(24, 24, 22, 0.22);
}

.kp-modal-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;
}

.kp-modal-head h2 {
  margin: 0;
  font-size: 17px;
}

.kp-subject {
  margin: 2px 0 0;
  font-size: 13px;
}

.kp-section {
  margin-top: 16px;
}

.kp-section h3 {
  margin: 0 0 8px;
  font-size: 14px;
}

.kp-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.kp-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  border: 1px solid var(--border, #e7e2d6);
  border-radius: 10px;
  padding: 7px 10px;
}

.kp-name {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
}

.kp-badge-primary {
  background: #d8efe4;
  color: #15803d;
}

.kp-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.kp-actions .btn {
  padding: 4px 8px;
}

.kp-add {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.kp-add .kp-selector {
  flex: 1;
}

.kp-tip {
  margin: 8px 0 0;
  font-size: 12px;
  line-height: 1.4;
}
</style>
