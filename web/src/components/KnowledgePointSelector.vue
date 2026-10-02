<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { knowledgePointsApi } from '@/api/knowledgePoints'
import type { KnowledgePoint, KnowledgePointNodeType } from '@/types'
import { nodeTypeIcon } from '@/utils/knowledgePoints'

const props = withDefaults(
  defineProps<{
    subject: string
    modelValue?: number | null
    // 需要从下拉中排除的知识点（例如题目已关联的）。
    excludeIds?: number[]
    disabled?: boolean
    placeholder?: string
    // P0：默认只允许选择可学习知识点（concept）；目录节点不可被选中。
    nodeType?: KnowledgePointNodeType
  }>(),
  {
    modelValue: null,
    excludeIds: () => [],
    disabled: false,
    placeholder: '选择结构化知识点',
    nodeType: 'concept',
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: number | null]
  select: [knowledgePoint: KnowledgePoint | null]
  loaded: [knowledgePoints: KnowledgePoint[]]
}>()

const items = ref<KnowledgePoint[]>([])
const loading = ref(false)
const loadedOnce = ref(false)
const error = ref('')
let requestSeq = 0

const available = computed(() => {
  const excluded = new Set(props.excludeIds)
  return items.value.filter((item) => !excluded.has(item.id))
})

const isEmpty = computed(() => loadedOnce.value && !loading.value && available.value.length === 0)

function onChange(event: Event) {
  const raw = (event.target as HTMLSelectElement).value
  const id = raw ? Number(raw) : null
  emit('update:modelValue', id)
  emit('select', id === null ? null : items.value.find((item) => item.id === id) ?? null)
}

async function load() {
  const subject = props.subject.trim()
  const seq = ++requestSeq
  error.value = ''
  items.value = []
  if (!subject) {
    loadedOnce.value = false
    loading.value = false
    return
  }
  loading.value = true
  try {
    const { data } = await knowledgePointsApi.list({ subject, node_type: props.nodeType })
    if (seq !== requestSeq) return
    items.value = data
    loadedOnce.value = true
    emit('loaded', data)
  } catch (err: any) {
    if (seq !== requestSeq) return
    error.value = err?.response?.data?.detail || '知识点加载失败'
    loadedOnce.value = true
  } finally {
    if (seq === requestSeq) loading.value = false
  }
}

watch(() => [props.subject, props.nodeType], load, { immediate: true })

defineExpose({ reload: load })
</script>

<template>
  <div class="kp-selector">
    <select
      class="select"
      :value="modelValue ?? ''"
      :disabled="disabled || loading || isEmpty"
      @change="onChange"
    >
      <option value="">{{ loading ? '加载中...' : placeholder }}</option>
      <option v-for="item in available" :key="item.id" :value="item.id">
        {{ nodeTypeIcon(item.node_type) }} {{ item.name }}
      </option>
    </select>
    <p v-if="error" class="text-danger kp-hint">{{ error }}</p>
    <p v-else-if="isEmpty" class="muted kp-hint">
      该学科暂未建立结构化知识点，可暂时使用文本知识点出题。
    </p>
  </div>
</template>

<style scoped>
.kp-selector {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.kp-hint {
  margin: 0;
  font-size: 12px;
  line-height: 1.4;
}
</style>
