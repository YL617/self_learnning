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
