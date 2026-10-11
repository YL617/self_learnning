<script setup lang="ts">
import { FileQuestion, Gauge, Layers, Network, TriangleAlert } from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { masteryApi, masteryLevel } from '@/api/mastery'
import { actionTone, recommendationsApi } from '@/api/recommendations'
import type { MasterySummary, RecommendationItem } from '@/types'

// M5 Step 1：用户端「我的学习计划」页。
// 数据全部来自既有只读接口（/mastery/summary、/recommendations/today），
// 不新增后端 API、不落任何业务表、不改推荐算法。
const router = useRouter()

const summary = ref<MasterySummary | null>(null)
const recommendations = ref<RecommendationItem[]>([])
const loading = ref(true)

async function load() {
  try {
    const [summaryRes, recRes] = await Promise.allSettled([
      masteryApi.summary(),
      recommendationsApi.today({ limit: 10 }),
    ])
    if (summaryRes.status === 'fulfilled') summary.value = summaryRes.value.data
    if (recRes.status === 'fulfilled') recommendations.value = recRes.value.data.items
  } finally {
    loading.value = false
  }
}

onMounted(load)

// 区域 A：掌握情况摘要（后端无记录时按 0 展示，不报错）
const masteredCount = computed(() => summary.value?.total ?? 0)
const averageScore = computed(() => Math.round(summary.value?.average_score ?? 0))
const weakCount = computed(() => summary.value?.weak_count ?? 0)
const averageLevel = computed(() => masteryLevel(averageScore.value))

// 区域 B：按 order 稳定排序
const ordered = computed(() => [...recommendations.value].sort((a, b) => a.order - b.order))

// 区域 C：跳转既有页面并携带知识点上下文（目标页面在 Step 3 接入该 query）
function goPractice(item: RecommendationItem) {
  router.push({ name: 'questions', query: { knowledge_point_id: item.knowledge_point_id } })
}

function goKnowledgePoint(item: RecommendationItem) {
  router.push({ name: 'knowledge', query: { knowledge_point_id: item.knowledge_point_id } })
}
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">今日学习计划</h1>
        <p class="page-subtitle">根据你的掌握情况与知识图谱自动生成，告诉你现在学什么、为什么学</p>
      </div>
    </div>

    <div v-if="loading" class="empty">正在生成学习计划...</div>
    <template v-else>
      <!-- 区域 A：我的学习状态 -->
      <div class="card">
        <h2>我的学习状态</h2>
        <div class="grid grid-3">
          <div class="stat-card">
            <div class="stat-icon plan-icon-learned"><Layers :size="22" /></div>
            <div>
              <div class="stat-value">{{ masteredCount }}</div>
              <div class="stat-label">已学习知识点</div>
            </div>
          </div>
          <div class="stat-card">
            <div class="stat-icon plan-icon-average"><Gauge :size="22" /></div>
            <div>
              <div class="stat-value">{{ averageScore }}%</div>
              <div class="stat-label">平均掌握度 · {{ averageLevel.label }}</div>
            </div>
          </div>
          <div class="stat-card">
            <div class="stat-icon plan-icon-weak"><TriangleAlert :size="22" /></div>
            <div>
              <div class="stat-value">{{ weakCount }}</div>
              <div class="stat-label">薄弱知识点</div>
            </div>
          </div>
        </div>
        <p v-if="!masteredCount" class="muted plan-hint">
          还没有掌握度记录：完成几道带知识点的练习后，这里会显示你的学习状态
        </p>
      </div>

      <!-- 区域 B + 区域 C：推荐学习 + 开始学习 -->
      <div class="card">
        <div class="row space-between plan-rec-head">
          <h2>推荐学习</h2>
          <span class="muted plan-rec-hint">按规则与知识图谱排序，可解释、非随机</span>
        </div>

        <div v-if="!ordered.length" class="empty">
          暂无学习建议：先给题目挂上知识点并作答，系统即可生成个性化推荐
        </div>
        <ol v-else class="plan-rec-list">
          <li
            v-for="item in ordered"
            :key="`${item.action}-${item.knowledge_point_id}`"
            class="plan-rec-item"
          >
            <div class="plan-rec-main">
              <div class="plan-rec-title">
                <span class="badge" :class="`tone-${actionTone(item.action).tone}`">
                  {{ item.action_label }}
                </span>
                <span class="plan-rec-name">{{ item.knowledge_point_name }}</span>
                <span class="muted plan-rec-meta">
                  {{ item.subject }} · 约 {{ item.estimated_minutes }} 分钟
                </span>
              </div>
              <p class="plan-rec-reason">推荐理由：{{ item.reason }}</p>
              <div class="muted plan-rec-score">推荐分数 {{ item.score }}</div>
            </div>
            <div class="row gap wrap plan-rec-actions">
              <button class="btn btn-primary" type="button" @click="goPractice(item)">
                <FileQuestion :size="15" />
                去练习
              </button>
              <button class="btn btn-outline" type="button" @click="goKnowledgePoint(item)">
                <Network :size="15" />
                查看知识点
              </button>
            </div>
          </li>
        </ol>
      </div>
    </template>
  </section>
</template>

<style scoped>
.plan-hint {
  margin: 14px 0 0;
  font-size: 12px;
}

.plan-icon-learned {
  background: var(--teal-soft);
  color: var(--teal);
}

.plan-icon-average {
  background: var(--primary-soft);
  color: var(--primary);
}

.plan-icon-weak {
  background: var(--danger-soft);
  color: var(--danger);
}

.plan-rec-head {
  margin-bottom: 12px;
}

.plan-rec-head h2 {
  margin: 0;
}

.plan-rec-hint {
  font-size: 12px;
}

.plan-rec-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.plan-rec-item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  flex-wrap: wrap;
}

.plan-rec-main {
  min-width: 0;
  flex: 1 1 260px;
}

.plan-rec-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.plan-rec-name {
  font-weight: 700;
  font-size: 15px;
  color: var(--text);
}

.plan-rec-meta {
  font-size: 12px;
}

.plan-rec-reason {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--text-2);
  overflow-wrap: anywhere;
}

.plan-rec-score {
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-3);
}

.plan-rec-actions {
  align-items: flex-start;
}

.tone-danger {
  background: var(--danger-soft);
  color: var(--danger);
}

.tone-amber {
  background: var(--amber-soft);
  color: var(--amber);
}

.tone-teal {
  background: var(--teal-soft);
  color: var(--teal);
}

.tone-neutral {
  background: var(--bg-deep);
  color: var(--text-2);
}
</style>
