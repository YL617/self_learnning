<script setup lang="ts">
import { FileQuestion, Sparkles } from 'lucide-vue-next'
import { onMounted, ref } from 'vue'

import { knowledgePointsApi, toKnowledgePointNameMap } from '@/api/knowledgePoints'
import { masteryApi } from '@/api/mastery'
import { questionsApi, type QuestionGeneratePayload } from '@/api/questions'
import KnowledgePointSelector from '@/components/KnowledgePointSelector.vue'
import MasteryBar from '@/components/MasteryBar.vue'
import QuestionCard from '@/components/QuestionCard.vue'
import QuestionKnowledgePointsModal from '@/components/QuestionKnowledgePointsModal.vue'
import type {
  KnowledgePoint,
  KnowledgePointMastery,
  KnowledgePointTag,
  Question,
  QuestionKnowledgePoint,
} from '@/types'

const form = ref({
  subject: '数据结构',
  knowledge_point: '栈和队列',
  knowledge_point_id: null as number | null,
  count: 5,
  question_type: 'choice' as 'choice' | 'fill' | 'short_answer',
})
const questions = ref<Question[]>([])
const loading = ref(false)
const error = ref('')
const success = ref('')

// Phase 2：结构化知识点名称映射 + 每题的关联缓存。
const kpNameById = ref<Record<number, string>>({})
const associationsByQuestion = ref<Record<number, QuestionKnowledgePoint[]>>({})
const manageOpen = ref(false)
const activeQuestion = ref<Question | null>(null)

// 大阶段 2：当前所选知识点的掌握度。
const selectedMastery = ref<KnowledgePointMastery | null>(null)
const masteryLoading = ref(false)

async function loadMastery() {
  const kpId = form.value.knowledge_point_id
  if (kpId == null) {
    selectedMastery.value = null
    return
  }
  masteryLoading.value = true
  try {
    const { data } = await masteryApi.get(kpId)
    // 切换知识点过程中可能已返回，避免写入过期结果。
    if (form.value.knowledge_point_id === kpId) selectedMastery.value = data
  } catch {
    // 404 = 尚未作答过该知识点，属正常空态。
    selectedMastery.value = null
  } finally {
    masteryLoading.value = false
  }
}

async function loadKpNames() {
  try {
    const { data } = await knowledgePointsApi.list()
    kpNameById.value = { ...kpNameById.value, ...toKnowledgePointNameMap(data) }
  } catch {
    // 名称解析失败不阻塞出题与列表展示（回退到旧文本知识点）。
  }
}

async function loadAssociations(questionIds: number[]) {
  const results = await Promise.allSettled(
    questionIds.map((id) => questionsApi.getQuestionKnowledgePoints(id)),
  )
  const next = { ...associationsByQuestion.value }
  results.forEach((result, index) => {
    if (result.status === 'fulfilled') {
      next[questionIds[index]] = result.value.data
    }
  })
  associationsByQuestion.value = next
}

function tagsFor(questionId: number): KnowledgePointTag[] {
  const items = associationsByQuestion.value[questionId] || []
  return items
    .filter((item) => kpNameById.value[item.knowledge_point_id])
    .map((item) => ({
      id: item.knowledge_point_id,
      name: kpNameById.value[item.knowledge_point_id],
      role: item.role,
    }))
}

function onKpSelect(kp: KnowledgePoint | null) {
  if (kp) {
    form.value.knowledge_point_id = kp.id
    form.value.knowledge_point = kp.name
  } else {
    form.value.knowledge_point_id = null
  }
  loadMastery()
}

// 手动修改文本名称后不再指向某个结构化知识点，避免发送不匹配的 id。
function onKpTextInput() {
  form.value.knowledge_point_id = null
  selectedMastery.value = null
}

// 答题后掌握度已在后端事务内更新，这里只做局部刷新。
function onAnswered(question: Question) {
  const tag = (associationsByQuestion.value[question.id] || [])[0]
  if (form.value.knowledge_point_id == null && tag) {
    form.value.knowledge_point_id = tag.knowledge_point_id
    if (kpNameById.value[tag.knowledge_point_id]) {
      form.value.knowledge_point = kpNameById.value[tag.knowledge_point_id]
    }
  }
  loadMastery()
}

async function generate() {
  loading.value = true
  error.value = ''
  success.value = ''
  try {
    const payload: QuestionGeneratePayload = {
      subject: form.value.subject,
      knowledge_point: form.value.knowledge_point,
      count: form.value.count,
      question_type: form.value.question_type,
      knowledge_point_id: form.value.knowledge_point_id ?? undefined,
    }
    const { data } = await questionsApi.generate(payload)
    questions.value = data
    success.value = `已生成 ${data.length} 道题目`
    await loadKpNames()
    await loadAssociations(data.map((item) => item.id))
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '生成失败'
  } finally {
    loading.value = false
  }
}

async function load() {
  try {
    const { data } = await questionsApi.list()
    questions.value = data
    await loadKpNames()
    await loadAssociations(data.map((item) => item.id))
  } catch {
    questions.value = []
  }
}

async function toggleFavorite(question: Question) {
  error.value = ''
  success.value = ''
  try {
    const { data } = await questionsApi.setFavorite(question.id, !question.is_favorite)
    const index = questions.value.findIndex((item) => item.id === question.id)
    if (index >= 0) questions.value[index] = data
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '收藏操作失败'
  }
}

async function removeQuestion(question: Question) {
  if (!window.confirm(`确定删除题目「${question.stem.slice(0, 20)}...」吗？删除后无法恢复。`)) return
  error.value = ''
  success.value = ''
  try {
    await questionsApi.remove(question.id)
    questions.value = questions.value.filter((item) => item.id !== question.id)
    success.value = '题目已删除'
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '删除失败'
  }
}

function openManage(question: Question) {
  activeQuestion.value = question
  manageOpen.value = true
}

function onAssociationsUpdated(questionId: number, associations: QuestionKnowledgePoint[]) {
  associationsByQuestion.value = {
    ...associationsByQuestion.value,
    [questionId]: associations,
  }
}

onMounted(load)
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">智能练习</h1>
        <p class="page-subtitle">按学科与知识点生成练习题，AI 自动判题并沉淀错题</p>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <h2><Sparkles :size="16" /> 生成题目</h2>
        <span class="badge badge-teal">AI 出题</span>
      </div>
      <div class="form-grid">
        <div class="field">
          <span>学科</span>
          <input v-model="form.subject" class="input" />
        </div>
        <div class="field">
          <span>知识点</span>
          <input
            v-model="form.knowledge_point"
            class="input"
            placeholder="输入知识点名称"
            @input="onKpTextInput"
          />
        </div>
        <div class="field">
          <span>结构化知识点（可选）</span>
          <KnowledgePointSelector
            :subject="form.subject"
            :model-value="form.knowledge_point_id"
            @select="onKpSelect"
          />
        </div>
        <div v-if="form.knowledge_point_id != null" class="field">
          <span>当前掌握度</span>
          <MasteryBar :score="selectedMastery?.mastery_score ?? null" :label="form.knowledge_point" />
          <p v-if="masteryLoading" class="muted mastery-hint">正在加载掌握度...</p>
        </div>
        <div class="field">
          <span>数量</span>
          <input v-model.number="form.count" class="input" type="number" min="1" max="20" />
        </div>
        <div class="field">
          <span>题型</span>
          <select v-model="form.question_type" class="select">
            <option value="choice">单选题</option>
            <option value="fill">填空题</option>
            <option value="short_answer">简答题</option>
          </select>
        </div>
      </div>
      <div class="generate-actions">
        <button class="btn btn-primary" type="button" :disabled="loading" @click="generate">
          <Sparkles :size="16" />
          {{ loading ? '生成中...' : '生成题目' }}
        </button>
        <p v-if="error" class="text-danger">{{ error }}</p>
        <p v-if="success" class="text-success">{{ success }}</p>
      </div>
    </div>

    <div v-if="questions.length">
      <div class="row space-between list-head">
        <h2><FileQuestion :size="16" /> 题目列表</h2>
        <span class="badge">{{ questions.length }} 道</span>
      </div>
      <div class="list">
        <QuestionCard
          v-for="question in questions"
          :key="question.id"
          :question="question"
          :show-manage="true"
          :knowledge-point-tags="tagsFor(question.id)"
          @favorite="toggleFavorite"
          @remove="removeQuestion"
          @manage="openManage"
          @answered="onAnswered"
        />
      </div>
    </div>
    <div v-else class="empty">还没有题目，先在上面生成一组吧</div>

    <QuestionKnowledgePointsModal
      :open="manageOpen"
      :question="activeQuestion"
      @close="manageOpen = false"
      @updated="onAssociationsUpdated"
    />
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

.generate-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 14px;
}

.generate-actions p {
  margin: 0;
}

.list-head {
  margin-bottom: 2px;
}

.list-head h2 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 7px;
}

.mastery-hint {
  margin: 0;
  font-size: 12px;
}
</style>
