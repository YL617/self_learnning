<script setup lang="ts">
import { CalendarCheck } from 'lucide-vue-next'
import { computed } from 'vue'

import { actionTone } from '@/api/recommendations'
import type { RecommendationItem } from '@/types'

const props = withDefaults(
  defineProps<{
    items: RecommendationItem[]
    loading?: boolean
    // 后端未生成任何建议时展示的空态文案
    emptyText?: string
  }>(),
  {
    loading: false,
    emptyText: '暂无学习建议：先建立知识点、给题目挂上知识点并作答后即可生成',
  },
)

const emit = defineEmits<{ (e: 'start', item: RecommendationItem): void }>()

const ordered = computed(() =>
  [...props.items].sort((a, b) => a.order - b.order),
)

// 打分分解项的中文名，用于向用户解释"为什么推荐这个"
const FACTOR_LABELS: Record<string, string> = {
  base: '动作基础分',
  urgency: '逾期紧迫度',
  gap: '掌握度缺口',
  goal: '目标命中',
  unlock: '解锁加成',
  recency: '最近练习折减',
}

function factorLines(item: RecommendationItem): string[] {
  return Object.entries(item.components ?? {})
    .filter(([, value]) => typeof value === 'number')
    .map(([key, value]) => `${FACTOR_LABELS[key] ?? key} ×${value.toFixed(2)}`)
}
</script>

<template>
  <div class="rec-card card">
    <div class="row space-between rec-head">
      <h2>今日学习建议</h2>
      <span class="muted rec-hint">按规则与知识图谱排序，可解释、非随机</span>
    </div>

    <div v-if="loading" class="empty">正在生成建议...</div>
    <div v-else-if="!ordered.length" class="empty">{{ emptyText }}</div>
    <ol v-else class="rec-list">
      <li v-for="item in ordered" :key="`${item.action}-${item.knowledge_point_id}`" class="rec-item">
        <div class="rec-main">
          <div class="rec-title">
            <span class="badge" :class="`tone-${actionTone(item.action).tone}`">
              {{ item.action_label }}
            </span>
            <span class="rec-name">{{ item.knowledge_point_name }}</span>
            <span class="muted rec-meta">
              {{ item.subject }} · 约 {{ item.estimated_minutes }} 分钟
            </span>
          </div>
          <p class="rec-reason">推荐理由：{{ item.reason }}</p>
          <details class="rec-factors">
            <summary>打分依据</summary>
            <span class="muted">{{ factorLines(item).join('、') }}（总分 {{ item.score }}）</span>
          </details>
        </div>
        <button class="btn btn-outline" type="button" @click="emit('start', item)">
          <CalendarCheck :size="15" />
          开始
        </button>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.rec-head {
  margin-bottom: 12px;
}

.rec-head h2 {
  margin: 0;
}

.rec-hint {
  font-size: 12px;
}

.rec-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.rec-item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
}

.rec-main {
  min-width: 0;
}

.rec-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.rec-name {
  font-weight: 700;
  font-size: 15px;
  color: var(--text);
}

.rec-meta {
  font-size: 12px;
}

.rec-reason {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--text-2);
  overflow-wrap: anywhere;
}

.rec-factors {
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-3);
}

.rec-factors summary {
  cursor: pointer;
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
