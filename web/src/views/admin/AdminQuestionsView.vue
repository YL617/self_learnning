<script setup lang="ts">
import { BarChart3, Plus, Sparkles, Trash2 } from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'

import { adminApi } from '@/api/admin'
import { knowledgePointsApi } from '@/api/knowledgePoints'
import KnowledgePointSelector from '@/components/KnowledgePointSelector.vue'
import type {
  AdminQuestion,
  AdminQuestionCreatePayload,
  AdminQuestionDetail,
  KnowledgeCoverage,
  KnowledgePoint,
  QuestionKnowledgePoint,
} from '@/types'

const items = ref<AdminQuestion[]>([])
const error = ref('')
const success = ref('')

// ---- M4：知识覆盖统计 ----
const coverage = ref<KnowledgeCoverage | null>(null)

// ---- M4：创建题目表单 ----
const formOpen = ref(true)
const form = ref({
  subject: '数据结构',
  knowledge_point: '',
  question_type: 'choice' as 'choice' | 'fill' | 'short_answer',
  stem: '',
  optionsText: '',
  answer: '',
  analysis: '',
  difficulty: '' as '' | 'easy' | 'medium' | 'hard',
  visibility: 'shared' as 'private' | 'shared',
})
// 已选知识点（仅 concept；第一个作为 primary）。
const selectedKps = ref<KnowledgePoint[]>([])
const creating = ref(false)

// 题目详情（点击“详情”懒加载）。
const detail = ref<{ questionId: number; data: AdminQuestionDetail } | null>(null)
const detailLoading = ref(false)

const kpNameById = ref<Record<number, string>>({})

const difficultyLabels: Record<string, string> = {
  easy: '简单',
  medium: '中等',
  hard: '困难',
}
const visibilityLabels: Record<string, string> = {
  private: '私有',
  shared: '共享',
}

const coveragePercent = computed(() => {
  if (!coverage.value || !coverage.value.concept_total) return 0
  return Math.round((coverage.value.covered / coverage.value.concept_total) * 100)
})

function parseOptions(): string[] {
  return form.value.optionsText
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
}

function onKpSelect(kp: KnowledgePoint | null) {
  if (!kp) return
  if (selectedKps.value.some((item) => item.id === kp.id)) return
  selectedKps.value = [...selectedKps.value, kp]
  if (!form.value.knowledge_point) form.value.knowledge_point = kp.name
}

function removeKp(id: number) {
  selectedKps.value = selectedKps.value.filter((item) => item.id !== id)
}

async function create() {
  error.value = ''
  success.value = ''
  if (!form.value.stem.trim() || !form.value.answer.trim()) {
    error.value = '题干与答案不能为空'
    return
  }
  if (!form.value.knowledge_point.trim() && !selectedKps.value.length) {
    error.value = '请填写知识点名称或选择结构化知识点'
    return
  }
  creating.value = true
  try {
    const payload: AdminQuestionCreatePayload = {
      subject: form.value.subject,
      knowledge_point: form.value.knowledge_point || selectedKps.value[0].name,
      question_type: form.value.question_type,
      stem: form.value.stem,
      options: parseOptions(),
      answer: form.value.answer,
      analysis: form.value.analysis || null,
      difficulty: form.value.difficulty || null,
      visibility: form.value.visibility,
      knowledge_point_ids: selectedKps.value.map((item) => item.id),
    }
    const { data } = await adminApi.createQuestion(payload)
    items.value = [data, ...items.value]
    success.value = `题目 #${data.id} 创建成功`
    form.value.stem = ''
    form.value.optionsText = ''
    form.value.answer = ''
    form.value.analysis = ''
    selectedKps.value = []
    await loadCoverage()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '创建失败'
  } finally {
    creating.value = false
  }
}

async function toggleDetail(item: AdminQuestion) {
  if (detail.value?.questionId === item.id) {
    detail.value = null
    return
  }
  detailLoading.value = true
  try {
    const { data } = await adminApi.getQuestion(item.id)
    detail.value = { questionId: item.id, data }
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '加载详情失败'
  } finally {
    detailLoading.value = false
  }
}

function kpLabel(kpId: number): string {
  return kpNameById.value[kpId] || `#${kpId}`
}

async function remove(item: AdminQuestion) {
  if (!window.confirm(`确定删除题目「${item.stem.slice(0, 30)}」吗？`)) return
  try {
    await adminApi.deleteQuestion(item.id)
    items.value = items.value.filter((row) => row.id !== item.id)
    if (detail.value?.questionId === item.id) detail.value = null
    await loadCoverage()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '删除失败'
  }
}

async function loadCoverage() {
  try {
    const { data } = await adminApi.knowledgeCoverage()
    coverage.value = data
  } catch {
    coverage.value = null
  }
}

async function load() {
  error.value = ''
  try {
    const { data } = await adminApi.questions()
    items.value = data
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '加载失败'
  }
  await loadCoverage()
  try {
    const { data } = await knowledgePointsApi.list()
    kpNameById.value = Object.fromEntries(data.map((item) => [item.id, item.name]))
  } catch {
    // 名称解析失败不阻塞详情展示（回退 #id）。
  }
}

onMounted(load)
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">题目管理</h1>
        <p class="page-subtitle">创建共享题库题目、绑定知识点并查看知识覆盖情况</p>
      </div>
    </div>
    <p v-if="error" class="text-danger">{{ error }}</p>
    <p v-if="success" class="text-success">{{ success }}</p>

    <!-- M4：知识覆盖统计（只统计 concept，目录不计入） -->
    <div v-if="coverage" class="card">
      <div class="card-head">
        <h2><BarChart3 :size="16" /> 知识覆盖</h2>
        <span class="badge badge-teal">{{ coveragePercent }}%</span>
      </div>
      <p class="muted coverage-summary">
        可学习知识点 {{ coverage.concept_total }} 个，已有题目覆盖
        {{ coverage.covered }} 个，未覆盖 {{ coverage.uncovered }} 个；题目共
        {{ coverage.question_total }} 道（含私有）。
      </p>
      <div v-if="coverage.items.length" class="table-wrap">
        <table class="admin-table">
          <thead>
            <tr>
              <th>学科</th>
              <th>知识点</th>
              <th>已覆盖</th>
              <th>未覆盖</th>
              <th>题目数</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in coverage.items" :key="row.subject">
              <td>{{ row.subject }}</td>
              <td>{{ row.concept_total }}</td>
              <td>{{ row.covered }}</td>
              <td>{{ row.uncovered }}</td>
              <td>{{ row.question_total }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- M4：创建题目 -->
    <div class="card">
      <div class="card-head">
        <h2><Sparkles :size="16" /> 创建题目</h2>
        <button class="btn btn-ghost" type="button" @click="formOpen = !formOpen">
          {{ formOpen ? '收起' : '展开' }}
        </button>
      </div>
      <div v-if="formOpen" class="form-grid">
        <div class="field">
          <span>学科</span>
          <input v-model="form.subject" class="input" />
        </div>
        <div class="field">
          <span>知识点（文本，可由下方选择自动带出）</span>
          <input v-model="form.knowledge_point" class="input" placeholder="如：循环单链表" />
        </div>
        <div class="field">
          <span>题型</span>
          <select v-model="form.question_type" class="select">
            <option value="choice">单选题</option>
            <option value="fill">填空题</option>
            <option value="short_answer">简答题</option>
          </select>
        </div>
        <div class="field">
          <span>难度（留空 = 按题型自动）</span>
          <select v-model="form.difficulty" class="select">
            <option value="">自动（choice=简单 / fill=中等 / 简答=困难）</option>
            <option value="easy">简单</option>
            <option value="medium">中等</option>
            <option value="hard">困难</option>
          </select>
        </div>
        <div class="field">
          <span>可见性</span>
          <select v-model="form.visibility" class="select">
            <option value="shared">共享（全部用户可练习）</option>
            <option value="private">私有（仅自己）</option>
          </select>
        </div>
        <div class="field">
          <span>绑定结构化知识点（仅 🧠 知识点，首个为主知识点）</span>
          <div class="kp-picker">
            <KnowledgePointSelector :subject="form.subject" @select="onKpSelect" />
            <div v-if="selectedKps.length" class="kp-chips">
              <span v-for="(kp, index) in selectedKps" :key="kp.id" class="badge badge-plain">
                {{ index === 0 ? '[主] ' : '' }}{{ kp.name }}
                <button class="chip-remove" type="button" @click="removeKp(kp.id)">×</button>
              </span>
            </div>
          </div>
        </div>
        <div class="field field-full">
          <span>题干</span>
          <textarea v-model="form.stem" class="textarea" rows="3" placeholder="输入题干" />
        </div>
        <div v-if="form.question_type === 'choice'" class="field field-full">
          <span>选项（每行一个，格式如「A. 选项内容」）</span>
          <textarea v-model="form.optionsText" class="textarea" rows="4" placeholder="A. 第一项&#10;B. 第二项" />
        </div>
        <div class="field field-full">
          <span>参考答案</span>
          <textarea v-model="form.answer" class="textarea" rows="2" placeholder="如：A" />
        </div>
        <div class="field field-full">
          <span>解析（可选）</span>
          <textarea v-model="form.analysis" class="textarea" rows="2" />
        </div>
      </div>
      <div class="generate-actions">
        <button class="btn btn-primary" type="button" :disabled="creating" @click="create">
          <Plus :size="16" />
          {{ creating ? '创建中...' : '创建题目' }}
        </button>
      </div>
    </div>

    <div v-if="!items.length" class="empty">暂无题目</div>
    <div v-else class="list">
      <div v-for="item in items" :key="item.id" class="card">
        <div class="row gap wrap" style="justify-content: space-between">
          <div class="row gap wrap">
            <span class="badge">{{ item.subject }}</span>
            <span class="badge badge-amber">{{ item.question_type }}</span>
            <span v-if="item.difficulty" class="badge">{{ difficultyLabels[item.difficulty] || item.difficulty }}</span>
            <span class="badge" :class="item.visibility === 'shared' ? 'badge-green' : 'badge-plain'">
              {{ visibilityLabels[item.visibility || 'private'] || item.visibility }}
            </span>
          </div>
          <div class="row gap">
            <button class="btn btn-ghost" type="button" @click="toggleDetail(item)">
              {{ detail?.questionId === item.id ? '收起详情' : '详情' }}
            </button>
            <button class="btn btn-danger" type="button" @click="remove(item)">
              <Trash2 :size="16" />
              删除
            </button>
          </div>
        </div>
        <p style="margin: 8px 0 0">{{ item.stem }}</p>
        <small class="muted">{{ item.knowledge_point }} · {{ item.created_at }}</small>

        <div v-if="detail?.questionId === item.id && !detailLoading" class="detail-box">
          <p><strong>参考答案：</strong>{{ detail.data.answer }}</p>
          <p v-if="detail.data.analysis"><strong>解析：</strong>{{ detail.data.analysis }}</p>
          <p v-if="detail.data.knowledge_points.length">
            <strong>关联知识点：</strong>
            <span v-for="qkp in detail.data.knowledge_points" :key="qkp.id" class="badge badge-plain">
              {{ qkp.role === 'primary' ? '[主] ' : '' }}{{ kpLabel(qkp.knowledge_point_id) }}
            </span>
          </p>
          <p v-else class="muted">尚未绑定结构化知识点</p>
        </div>
      </div>
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
  display: flex;
  align-items: center;
  gap: 7px;
}

.coverage-summary {
  margin: 0 0 10px;
  font-size: 13px;
}

.form-grid .field-full {
  grid-column: 1 / -1;
}

.kp-picker {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.kp-chips {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.chip-remove {
  border: none;
  background: transparent;
  color: inherit;
  cursor: pointer;
  padding: 0 0 0 2px;
  font-weight: 700;
}

.generate-actions {
  margin-top: 14px;
}

.detail-box {
  margin-top: 10px;
  padding: 10px;
  border-radius: 8px;
  background: var(--surface-muted, #f3f1e9);
  font-size: 13px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.detail-box p {
  margin: 0;
}
</style>
