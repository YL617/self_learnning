<script setup lang="ts">
import { BookOpenText, ChevronDown, ChevronRight, Network } from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { knowledgePointsApi } from '@/api/knowledgePoints'
import { masteryApi } from '@/api/mastery'
import MasteryBar from '@/components/MasteryBar.vue'
import QuestionCard from '@/components/QuestionCard.vue'
import type { KnowledgePoint, KnowledgePointMastery, Question } from '@/types'
import { buildRows, nodeTypeIcon, type KnowledgePointRow } from '@/utils/knowledgePoints'

// 全量加载（含 container + concept），前端按学科过滤并展示层级树。
const route = useRoute()
const allItems = ref<KnowledgePoint[]>([])
const subject = ref('')
const error = ref('')
const loading = ref(false)

// 折叠的 container id 集合；折叠后其全部后代不显示。
const collapsed = ref<Set<number>>(new Set())

// 当前选中的 concept（container 永不可选）。
const selected = ref<KnowledgePoint | null>(null)
const selectedMastery = ref<KnowledgePointMastery | null>(null)
const questions = ref<Question[]>([])
const detailLoading = ref(false)

const subjects = computed(() =>
  Array.from(new Set(allItems.value.map((item) => item.subject))).sort(),
)

const rows = computed<KnowledgePointRow[]>(() =>
  buildRows(allItems.value, { subject: subject.value }),
)

// 折叠语义：某行的任一祖先是折叠状态则隐藏。
const visibleRows = computed<KnowledgePointRow[]>(() => {
  const byId = new Map(allItems.value.map((item) => [item.id, item]))
  return rows.value.filter((row) => {
    let cursor = row.parent_id ?? null
    const seen = new Set<number>([row.id])
    while (cursor !== null && byId.has(cursor) && !seen.has(cursor)) {
      if (collapsed.value.has(cursor)) return false
      seen.add(cursor)
      cursor = byId.get(cursor)!.parent_id ?? null
    }
    return true
  })
})

function rowDepthStyle(depth: number): { paddingLeft: string } {
  return { paddingLeft: `${depth * 18 + 8}px` }
}

function toggleCollapse(row: KnowledgePointRow) {
  // 只有 container 可折叠（有子节点才有意义，但仍允许统一切换图标状态）。
  const next = new Set(collapsed.value)
  if (next.has(row.id)) next.delete(row.id)
  else next.add(row.id)
  collapsed.value = next
}

function selectConcept(row: KnowledgePointRow) {
  // 双保险：container 不进详情（后端另有 DB 级禁令）。
  if (row.node_type !== 'concept') return
  if (selected.value?.id === row.id) return
  selected.value = row
  loadDetail()
}

async function loadDetail() {
  const kp = selected.value
  if (!kp) return
  detailLoading.value = true
  try {
    const [questionsRes, masteryRes] = await Promise.allSettled([
      knowledgePointsApi.questions(kp.id),
      masteryApi.get(kp.id),
    ])
    // 切换过程中可能已选中其他节点，避免写入过期结果。
    if (selected.value?.id !== kp.id) return
    questions.value =
      questionsRes.status === 'fulfilled' ? questionsRes.value.data : []
    // 404 = 尚未作答过，属正常空态。
    selectedMastery.value = masteryRes.status === 'fulfilled' ? masteryRes.value.data : null
  } finally {
    detailLoading.value = false
  }
}

// 答题后掌握度已在后端事务内更新，局部刷新即可。
function onAnswered() {
  if (selected.value) loadDetail()
}

// M5 Step 3：消费 /knowledge?knowledge_point_id=xxx —— 自动展开祖先并定位选中该知识点。
function expandAncestors(id: number) {
  const byId = new Map(allItems.value.map((item) => [item.id, item]))
  const next = new Set(collapsed.value)
  let cursor = byId.get(id)?.parent_id ?? null
  const seen = new Set<number>([id])
  while (cursor !== null && byId.has(cursor) && !seen.has(cursor)) {
    next.delete(cursor)
    seen.add(cursor)
    cursor = byId.get(cursor)!.parent_id ?? null
  }
  collapsed.value = next
}

function applyRouteQuery() {
  const raw = route.query.knowledge_point_id
  const value = Array.isArray(raw) ? raw[0] : raw
  const id = Number(value)
  // 非法 query（缺省 / 非数字 / 非正数）直接忽略，既有默认行为不变。
  if (!value || !Number.isFinite(id) || id <= 0) return
  // 在未按学科过滤的全量行中查找，避免目标不在当前学科时定位失败。
  const row = buildRows(allItems.value).find((item) => item.id === id)
  // container 不可进详情（前端双保险；后端另有 DB 级禁令）。
  if (!row || row.node_type !== 'concept') return
  if (row.subject && subject.value !== row.subject) subject.value = row.subject
  expandAncestors(id)
  selectConcept(row)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await knowledgePointsApi.list()
    allItems.value = data
    if (!subject.value && subjects.value.length) {
      subject.value = subjects.value.includes('数据结构') ? '数据结构' : subjects.value[0]
    }
    applyRouteQuery()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '知识点加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title"><Network :size="18" /> 知识图谱</h1>
        <p class="page-subtitle">浏览学科知识树，查看知识点掌握度并练习关联题目</p>
      </div>
    </div>
    <p v-if="error" class="text-danger">{{ error }}</p>

    <div class="explore-layout">
      <div class="card tree-card">
        <div class="card-head">
          <h2><BookOpenText :size="16" /> 知识树</h2>
          <select v-model="subject" class="select tree-subject">
            <option v-for="item in subjects" :key="item" :value="item">{{ item }}</option>
          </select>
        </div>
        <p v-if="loading" class="muted">加载中...</p>
        <div v-else-if="!visibleRows.length" class="empty">该学科暂无知识点</div>
        <ul v-else class="tree">
          <li
            v-for="row in visibleRows"
            :key="row.id"
            class="tree-item"
            :class="{
              'is-container': row.node_type === 'container',
              'is-selected': selected?.id === row.id,
            }"
            :style="rowDepthStyle(row.depth)"
          >
            <button
              class="tree-btn"
              type="button"
              @click="row.node_type === 'container' ? toggleCollapse(row) : selectConcept(row)"
            >
              <span v-if="row.node_type === 'container'" class="tree-caret">
                <ChevronDown v-if="!collapsed.has(row.id)" :size="14" />
                <ChevronRight v-else :size="14" />
              </span>
              <span v-else class="tree-caret tree-caret-leaf" />
              <span class="tree-name">
                {{ nodeTypeIcon(row.node_type) }} {{ row.name }}
              </span>
              <span v-if="row.difficulty" class="badge">{{ row.difficulty }}</span>
            </button>
          </li>
        </ul>
      </div>

      <div class="detail-panel">
        <div v-if="!selected" class="card">
          <div class="empty">
            在左侧选择一个知识点（🧠），查看掌握度与关联题目<br />
            <small class="muted">📁 目录仅用于组织层级，不可直接练习</small>
          </div>
        </div>
        <template v-else>
          <div class="card">
            <div class="card-head">
              <h2>{{ selected.name }}</h2>
              <span class="badge">{{ selected.code || selected.subject }}</span>
            </div>
            <p v-if="selected.description" class="detail-desc">{{ selected.description }}</p>
            <div class="detail-meta">
              <span v-if="selected.difficulty" class="badge badge-amber">难度：{{ selected.difficulty }}</span>
              <span v-if="selected.estimated_minutes" class="badge">
                预计 {{ selected.estimated_minutes }} 分钟
              </span>
              <span class="badge badge-teal">关联题目 {{ questions.length }} 道</span>
            </div>
            <MasteryBar
              :score="selectedMastery?.mastery_score ?? null"
              :label="selected.name"
            />
            <p v-if="selectedMastery" class="muted mastery-hint">
              作答 {{ selectedMastery.attempt_count }} 次 · 正确 {{ selectedMastery.correct_count }} 次 ·
              当前连胜 {{ selectedMastery.correct_streak }}
            </p>
          </div>

          <p v-if="detailLoading" class="muted">加载题目中...</p>
          <div v-else-if="!questions.length" class="empty">该知识点暂无关联题目</div>
          <div v-else class="list">
            <QuestionCard
              v-for="question in questions"
              :key="question.id"
              :question="question"
              :knowledge-point-tags="[{ id: selected.id, name: selected.name, role: 'primary' }]"
              @answered="onAnswered"
            />
          </div>
        </template>
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

.explore-layout {
  display: grid;
  grid-template-columns: minmax(280px, 380px) 1fr;
  gap: 16px;
  align-items: start;
}

@media (max-width: 1000px) {
  .explore-layout {
    grid-template-columns: 1fr;
  }
}

.tree-card {
  max-height: 72vh;
  overflow: auto;
}

.tree-subject {
  max-width: 160px;
}

.tree {
  list-style: none;
  margin: 0;
  padding: 0;
}

.tree-item {
  display: flex;
}

.tree-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  width: 100%;
  padding: 6px 8px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text);
  cursor: pointer;
  text-align: left;
  font-size: 14px;
}

.tree-btn:hover {
  background: var(--surface-muted, #f3f1e9);
}

.tree-item.is-container .tree-name {
  font-weight: 700;
}

.tree-item.is-selected .tree-btn {
  background: #d8efe4;
  color: #15803d;
  font-weight: 700;
}

.tree-caret {
  display: inline-flex;
  width: 16px;
  flex-shrink: 0;
  color: #8a887e;
}

.tree-caret-leaf::before {
  content: '•';
}

.detail-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.detail-desc {
  margin: 0 0 10px;
  font-size: 13px;
  color: #57564f;
}

.detail-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.mastery-hint {
  margin: 8px 0 0;
  font-size: 12px;
}
</style>
