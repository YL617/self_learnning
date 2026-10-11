<script setup lang="ts">
import { computed } from 'vue'

import type { RecommendationItem } from '@/types'

// M5 Step 3：推荐理由展示组件（纯展示）。
// 数据全部来自后端已生成的 item.reason / item.components，
// 不改推荐算法、不改后端 reason 文案、不新增后端 API。
const props = withDefaults(
  defineProps<{
    item?: Pick<RecommendationItem, 'reason' | 'components' | 'score'> | null
  }>(),
  { item: null },
)

// 后端 reason 是「；」拼接的多因子说明，这里拆成逐条可读的理由行。
const reasons = computed<string[]>(() =>
  (props.item?.reason ?? '')
    .split(/[；;]/)
    .map((part) => part.trim())
    .filter(Boolean),
)

// 打分分解项的中文名（与 RecommendationCard 保持同一套口径，纯前端展示用）。
const FACTOR_LABELS: Record<string, string> = {
  base: '动作基础分',
  urgency: '逾期紧迫度',
  gap: '掌握度缺口',
  goal: '目标命中',
  unlock: '解锁加成',
  recency: '最近练习折减',
}

const factors = computed<string[]>(() =>
  Object.entries(props.item?.components ?? {})
    .filter(([, value]) => typeof value === 'number')
    .map(([key, value]) => `${FACTOR_LABELS[key] ?? key} ×${value.toFixed(2)}`),
)
</script>

<template>
  <div class="rec-reason">
    <template v-if="reasons.length">
      <p class="rec-reason-label">推荐原因</p>
      <ul class="rec-reason-list">
        <li v-for="(reason, index) in reasons" :key="index" class="rec-reason-item">
          {{ reason }}
        </li>
      </ul>
    </template>
    <p v-else class="muted rec-reason-empty">
      系统暂未给出推荐理由：该知识点还没有掌握度与作答记录，先完成一次练习即可生成
    </p>

    <details v-if="factors.length" class="rec-reason-factors">
      <summary>打分依据</summary>
      <span class="muted">{{ factors.join('、') }}（总分 {{ item?.score }}）</span>
    </details>
  </div>
</template>

<style scoped>
.rec-reason-label {
  margin: 6px 0 0;
  font-size: 12px;
  font-weight: 700;
  color: var(--text-2);
}

.rec-reason-list {
  list-style: none;
  margin: 4px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.rec-reason-item {
  position: relative;
  padding-left: 12px;
  font-size: 13px;
  color: var(--text-2);
  overflow-wrap: anywhere;
}

.rec-reason-item::before {
  content: '·';
  position: absolute;
  left: 2px;
  color: var(--text-3);
}

.rec-reason-empty {
  margin: 6px 0 0;
  font-size: 12px;
}

.rec-reason-factors {
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-3);
}

.rec-reason-factors summary {
  cursor: pointer;
}
</style>
