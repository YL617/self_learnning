<script setup lang="ts">
import { computed } from 'vue'

import { masteryLevel } from '@/api/mastery'

const props = withDefaults(
  defineProps<{
    score?: number | null
    label?: string
    // 无记录时展示的文案（后端未产生掌握度记录）。
    emptyText?: string
    compact?: boolean
  }>(),
  {
    score: null,
    label: '掌握度',
    emptyText: '暂无掌握度记录',
    compact: false,
  },
)

const hasScore = computed(() => typeof props.score === 'number' && !Number.isNaN(props.score))

const bounded = computed(() => {
  if (!hasScore.value) return 0
  return Math.max(0, Math.min(100, Math.round(props.score as number)))
})

const level = computed(() => masteryLevel(bounded.value))
</script>

<template>
  <div class="mastery-bar" :class="{ 'is-compact': compact }">
    <template v-if="hasScore">
      <div class="mastery-head">
        <span class="mastery-label">{{ label }}</span>
        <span class="mastery-score">{{ bounded }}%</span>
        <span class="mastery-level" :class="`tone-${level.tone}`">{{ level.label }}</span>
      </div>
      <div
        class="mastery-track"
        role="progressbar"
        :aria-valuenow="bounded"
        aria-valuemin="0"
        aria-valuemax="100"
        :aria-label="`${label} ${bounded}%`"
      >
        <div class="mastery-fill" :class="`tone-${level.tone}`" :style="{ width: `${bounded}%` }" />
      </div>
    </template>
    <p v-else class="mastery-empty">{{ emptyText }}</p>
  </div>
</template>

<style scoped>
.mastery-bar {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 180px;
}

.mastery-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-2);
}

.mastery-label {
  color: var(--text-2);
}

.mastery-score {
  font-weight: 700;
  font-size: 13px;
  color: var(--text);
}

.mastery-level {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 999px;
}

.tone-weak {
  background: var(--danger-soft);
  color: var(--danger);
}

.tone-steady {
  background: var(--amber-soft);
  color: var(--amber);
}

.tone-strong {
  background: var(--success-soft);
  color: var(--success);
}

.mastery-track {
  height: 6px;
  border-radius: 999px;
  background: var(--bg-deep);
  overflow: hidden;
}

.mastery-fill {
  height: 100%;
  border-radius: 999px;
  transition: width 0.25s ease;
}

.mastery-fill.tone-weak {
  background: var(--danger);
}

.mastery-fill.tone-steady {
  background: var(--amber);
}

.mastery-fill.tone-strong {
  background: var(--success);
}

.mastery-empty {
  margin: 0;
  font-size: 12px;
  color: var(--text-3);
}

.is-compact .mastery-head {
  font-size: 11px;
}
</style>
