<template>
  <view class="page">
    <view class="card">
      <text class="card-title">错题本</text>
      <view v-if="!items.length" class="empty">还没有错题</view>
      <view v-for="item in items" :key="item.id" class="wrong-card">
        <text class="stem">{{ item.question?.stem }}</text>
        <text class="muted">{{ item.question?.analysis }}</text>
        <text v-if="!item.mastered && item.next_review_date" class="muted">
          阶段 {{ item.review_stage }}/5 · 下次复习 {{ item.next_review_date }}
        </text>
        <view class="row gap">
          <button class="btn outline" @click="retry(item)">举一反三</button>
          <button v-if="!item.mastered" class="btn teal" @click="review(item)">复习一次</button>
          <button class="btn ghost" @click="toggle(item)">
            {{ item.mastered ? "取消掌握" : "标记掌握" }}
          </button>
        </view>
      </view>
    </view>

    <view v-if="generated.length" class="card">
      <text class="card-title">同类练习</text>
      <view v-for="question in generated" :key="question.id" class="wrong-card">
        <text class="stem">{{ question.stem }}</text>
        <text class="muted">{{ question.answer }}</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { ref } from "vue";

import { api } from "@/api/request";
import type { Question, WrongBookItem } from "@/types";

const items = ref<WrongBookItem[]>([]);
const generated = ref<Question[]>([]);

async function load() {
  try {
    items.value = await api.wrongBook();
  } catch {
    items.value = [];
  }
}

async function toggle(item: WrongBookItem) {
  await api.markMastered(item.id, !item.mastered);
  await load();
}

async function review(item: WrongBookItem) {
  await api.markMastered(item.id, item.mastered);
  await load();
}

async function retry(item: WrongBookItem) {
  if (!item.question) return;
  generated.value = await api.generateQuestions({
    subject: item.question.subject,
    knowledge_point: item.question.knowledge_point,
    count: 3,
    question_type: "choice",
  });
}

onShow(load);
</script>

<style scoped>
.page {
  padding: 20rpx;
}

.card {
  background: #fff;
  border-radius: 16rpx;
  padding: 24rpx;
  margin-bottom: 20rpx;
}

.card-title {
  font-size: 30rpx;
  font-weight: 700;
  display: block;
  margin-bottom: 20rpx;
}

.empty {
  color: #5b6b7a;
  text-align: center;
  padding: 40rpx 0;
}

.wrong-card {
  border: 1px solid #dde3e8;
  border-radius: 12rpx;
  padding: 20rpx;
  margin-bottom: 16rpx;
}

.stem {
  display: block;
  font-size: 28rpx;
  line-height: 1.6;
  margin-bottom: 10rpx;
}

.muted {
  display: block;
  color: #5b6b7a;
  font-size: 24rpx;
  margin-bottom: 12rpx;
}

.row {
  display: flex;
  gap: 12rpx;
}

.btn {
  flex: 1;
  border-radius: 12rpx;
  padding: 14rpx;
  font-size: 24rpx;
  font-weight: 600;
}

.btn.outline {
  border: 1px solid #2563eb;
  color: #2563eb;
  background: #fff;
}

.btn.teal {
  background: #0f766e;
  color: #fff;
}

.btn.ghost {
  border: 1px solid #dde3e8;
  color: #5b6b7a;
  background: #fff;
}
</style>
