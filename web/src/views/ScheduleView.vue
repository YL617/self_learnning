<script setup lang="ts">
import { CalendarDays, ClipboardList } from 'lucide-vue-next'
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import CalendarPanel from '@/components/schedule/CalendarPanel.vue'
import TodoPanel from '@/components/schedule/TodoPanel.vue'

type PanelTab = 'todo' | 'calendar'

const route = useRoute()
const router = useRouter()
const activeTab = ref<PanelTab>(
  route.query.tab === 'calendar' ? 'calendar' : 'todo',
)

function switchTab(tab: PanelTab) {
  activeTab.value = tab
  void router.replace({ query: { tab } })
}
</script>

<template>
  <section class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">待办与日历</h1>
        <p class="page-subtitle">记录每日任务，用年 / 月 / 日视图查看学习安排</p>
      </div>
      <div class="segmented">
        <button
          type="button"
          :class="{ active: activeTab === 'todo' }"
          @click="switchTab('todo')"
        >
          <ClipboardList :size="15" />
          待办
        </button>
        <button
          type="button"
          :class="{ active: activeTab === 'calendar' }"
          @click="switchTab('calendar')"
        >
          <CalendarDays :size="15" />
          日历
        </button>
      </div>
    </div>

    <TodoPanel v-show="activeTab === 'todo'" />
    <CalendarPanel v-show="activeTab === 'calendar'" />
  </section>
</template>

<style scoped>
.segmented {
  display: inline-flex;
  gap: 2px;
  padding: 3px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: #f1f4f7;
}

.segmented button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: none;
  background: transparent;
  padding: 6px 14px;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-2);
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease, box-shadow 0.15s ease;
}

.segmented button:hover {
  color: var(--primary);
}

.segmented button.active {
  background: #fff;
  color: var(--primary);
  box-shadow: var(--shadow);
}

@media (max-width: 600px) {
  .segmented {
    width: 100%;
  }

  .segmented button {
    flex: 1;
    justify-content: center;
  }
}
</style>
