<script setup lang="ts">
import { computed } from 'vue'

import MasteryBar from '@/components/MasteryBar.vue'
import type { LearningPath, LearningPathStep } from '@/types'

// M5 Step 2：学习路径时间线（纯展示组件）。
// 数据来自既有只读接口 GET /knowledge-points/{id}/path，不新增后端 API、不改算法。
const props = withDefaults(
  defineProps<{
    path?: LearningPath | null
    loading?: boolean
    emptyText?: string
  }>(),
  {
    path: null,
    loading: false,
    emptyText: '暂无可展示的学习路径：先从推荐列表选择一个知识点',
  },
)

// 后端已按拓扑序返回，这里再稳定排序一次（防御性，不改变语义）
const steps = computed<LearningPathStep[]>(() =>
  [...(props.path?.steps ?? [])].sort((a, b) => a.order - b.order),
)

// 「当前知识点」= 第一个未满足的步骤；全部满足时即目标节点
const currentId = computed<number | null>(() => {
  const first = steps.value.find((step) => !step.satisfied)
  if (first) return first.knowledge_point.id
  return steps.value.find((step) => step.is_target)?.knowledge_point.id ?? null
})

// 「是否已解锁」（近似）：该步之前的所有步骤均已满足。
// 说明：真实阻塞只看 strength>=60 的硬前置，而 /path 未下发 strength，故为近似提示。
function unlockedBefore(index: number): boolean {
  return steps.value.slice(0, index).every((step) => step.satisfied)
}

function isContainer(step: LearningPathStep): boolean {
  return step.knowledge_point.node_type === 'container'
}

function unlockText(step: LearningPathStep, index: number): string {
  if (step.satisfied) return '已解锁'
  return unlockedBefore(index) ? '前置已满足，可开始' : '存在未满足前置'
}
</script>

<template>
  <div class="path-timeline">
    <div v-if="loading" class="empty">正在加载学习路径...</div>
    <div v-else-if="!steps.length" class="empty">{{ emptyText }}</div>
    <template v-else>
      <div class="path-head">
        <span class="path-goal">目标：{{ path?.target.name }}</span>
        <span class="badge" :class="path?.ready ? 'badge-green' : 'badge-amber'">
          {{ path?.ready ? '可开始' : '有待满足前置' }}
        </span>
        <span class="muted path-threshold">掌握度 ≥ {{ path?.threshold ?? 70 }} 视为已满足</span>
      </div>

      <ol class="path-steps">
        <li
          v-for="(step, index) in steps"
          :key="step.knowledge_point.id"
          class="path-step"
          :class="{
            'is-current': step.knowledge_point.id === currentId,
            'is-target': step.is_target,
          }"
        >
          <div class="path-marker">{{ step.order }}</div>
          <div class="path-body">
            <div class="path-title">
              <span class="path-name">{{ step.knowledge_point.name }}</span>
              <span
                class="path-type-chip"
                :class="isContainer(step) ? 'is-container' : 'is-concept'"
              >
                {{ isContainer(step) ? '目录' : '可学习' }}
              </span>
              <span
                class="badge"
                :class="step.is_target || step.satisfied ? 'badge-green' : 'badge-amber'"
              >
                {{ step.is_target ? '目标' : step.satisfied ? '已满足' : '待掌握' }}
              </span>
              <span
                v-if="step.knowledge_point.id === currentId && !step.is_target"
                class="badge badge-teal"
              >
                当前
              </span>
            </div>

            <div class="muted path-meta">
              {{ step.knowledge_point.subject }}
              <template v-if="step.knowledge_point.estimated_minutes">
                · 约 {{ step.knowledge_point.estimated_minutes }} 分钟
              </template>
              · {{ unlockText(step, index) }}
            </div>

            <MasteryBar
              :score="step.mastery_score ?? null"
              label="掌握度"
              compact
            />

            <p v-if="isContainer(step)" class="muted path-warn">
              目录节点仅用于组织层级，不可直接练习
            </p>
          </div>
        </li>
      </ol>
    </template>
  </div>
</template>

<style scoped>
.path-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.path-goal {
  font-weight: 700;
  font-size: 14px;
  color: var(--text);
}

.path-threshold {
  font-size: 12px;
}

.path-steps {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
}

.path-step {
  position: relative;
  display: flex;
  gap: 12px;
  padding: 0 0 14px 0;
}

.path-step:last-child {
  padding-bottom: 0;
}

/* 连接线 */
.path-step:not(:last-child)::before {
  content: '';
  position: absolute;
  left: 13px;
  top: 26px;
  bottom: 0;
  width: 2px;
  background: var(--border);
}

.path-marker {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border-radius: 999px;
  display: grid;
  place-items: center;
  font-size: 12px;
  font-weight: 700;
  background: var(--bg-deep);
  color: var(--text-2);
  z-index: 1;
}

.path-step.is-current .path-marker {
  background: var(--teal-soft);
  color: var(--teal);
}

.path-step.is-target .path-marker {
  background: var(--success-soft);
  color: var(--success);
}

.path-body {
  min-width: 0;
  flex: 1;
  padding: 4px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
}

.path-step.is-target .path-body {
  border-color: var(--success);
}

.path-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.path-name {
  font-weight: 700;
  font-size: 14px;
  color: var(--text);
}

.path-type-chip {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 999px;
}

.path-type-chip.is-concept {
  background: var(--teal-soft);
  color: var(--teal);
}

.path-type-chip.is-container {
  background: var(--bg-deep);
  color: var(--text-2);
}

.path-meta {
  margin: 4px 0 6px;
  font-size: 12px;
}

.path-warn {
  margin: 6px 0 0;
  font-size: 12px;
}
</style>
