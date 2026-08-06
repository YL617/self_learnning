<template>
  <view class="page">
    <view class="card">
      <text class="card-title">生成题目</text>
      <view class="field">
        <text>学科</text>
        <input v-model="form.subject" class="input" />
      </view>
      <view class="field">
        <text>知识点</text>
        <input v-model="form.knowledge_point" class="input" />
      </view>
      <view class="row">
        <view class="field half">
          <text>数量</text>
          <input v-model.number="form.count" class="input" type="number" />
        </view>
        <view class="field half">
          <text>题型</text>
          <picker :range="types" @change="onTypeChange">
            <view class="input">{{ types[typeIndex] }}</view>
          </picker>
        </view>
      </view>
      <button class="btn primary" :disabled="loading" @click="generate">
        {{ loading ? "生成中..." : "生成题目" }}
      </button>
      <text v-if="message" class="message">{{ message }}</text>
    </view>

    <view class="card">
      <text class="card-title">题目列表</text>
      <view v-if="!questions.length" class="empty">还没有题目</view>
      <view v-for="question in questions" :key="question.id" class="question-card">
        <view class="row gap">
          <text class="badge">{{ question.subject }}</text>
          <text class="badge teal">{{ question.question_type }}</text>
          <text
            class="action-link"
            :class="{ favorited: question.is_favorite }"
            @click="favorite(question)"
          >
            {{ question.is_favorite ? "已收藏" : "收藏" }}
          </text>
          <text class="delete-link" @click="removeQuestion(question)">删除</text>
        </view>
        <text class="stem">{{ question.stem }}</text>
        <view v-if="options(question).length" class="options">
          <view
            v-for="option in options(question)"
            :key="option"
            class="option"
            @click="choose(question, option)"
          >
            <text>{{ option }}</text>
          </view>
        </view>
        <input
          v-else
          v-model="answers[question.id]"
          class="input"
          placeholder="输入答案"
        />
        <button
          class="btn outline"
          @click="submit(question)"
        >
          {{ results[question.id] === undefined ? "提交答案" : results[question.id] ? "回答正确" : "回答错误" }}
        </button>
        <text v-if="showAnalysis[question.id]" class="analysis">{{ question.analysis }}</text>
        <text class="link" @click="toggleAnalysis(question)">查看解析</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { reactive, ref } from "vue";

import { api } from "@/api/request";
import type { Question } from "@/types";

const types = ["choice", "fill", "short_answer"];
const typeIndex = ref(0);
const form = ref({
  subject: "数据结构",
  knowledge_point: "栈和队列",
  count: 5,
  question_type: "choice" as "choice" | "fill" | "short_answer",
});
const questions = ref<Question[]>([]);
const answers = reactive<Record<number, string>>({});
const results = reactive<Record<number, boolean | undefined>>({});
const showAnalysis = reactive<Record<number, boolean>>({});
const loading = ref(false);
const message = ref("");

function onTypeChange(event: { detail: { value: string } }) {
  typeIndex.value = Number(event.detail.value);
  form.value.question_type = types[typeIndex.value] as "choice" | "fill" | "short_answer";
}

function options(question: Question): string[] {
  if (!question.options_json) return [];
  try {
    const parsed = JSON.parse(question.options_json);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function choose(question: Question, option: string) {
  answers[question.id] = option.split(".")[0].trim();
}

async function generate() {
  loading.value = true;
  message.value = "";
  try {
    questions.value = await api.generateQuestions(form.value);
    message.value = `已生成 ${questions.value.length} 道题目`;
  } catch (err: any) {
    message.value = err?.detail || "生成失败";
  } finally {
    loading.value = false;
  }
}

async function submit(question: Question) {
  if (!answers[question.id]) return;
  const result = await api.submitAnswer(question.id, answers[question.id]);
  results[question.id] = result.is_correct;
}

async function favorite(question: Question) {
  try {
    const updated = await api.setQuestionFavorite(question.id, !question.is_favorite);
    question.is_favorite = updated.is_favorite;
  } catch (err: any) {
    message.value = err?.detail || "收藏失败";
  }
}

function removeQuestion(question: Question) {
  uni.showModal({
    title: "删除题目",
    content: `确定删除这道题目吗？删除后无法恢复。`,
    success: async (res) => {
      if (!res.confirm) return;
      try {
        await api.deleteQuestion(question.id);
        questions.value = questions.value.filter((item) => item.id !== question.id);
        message.value = "题目已删除";
      } catch (err: any) {
        message.value = err?.detail || "删除失败";
      }
    },
  });
}

function toggleAnalysis(question: Question) {
  showAnalysis[question.id] = !showAnalysis[question.id];
}
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

.field {
  display: flex;
  flex-direction: column;
  gap: 8rpx;
  margin-bottom: 16rpx;
  color: #5b6b7a;
}

.row {
  display: flex;
  gap: 16rpx;
}

.gap {
  gap: 8rpx;
}

.half {
  flex: 1;
}

.input {
  border: 1px solid #dde3e8;
  border-radius: 12rpx;
  padding: 14rpx;
  font-size: 26rpx;
}

.btn {
  width: 100%;
  border-radius: 12rpx;
  padding: 14rpx;
  font-size: 26rpx;
  font-weight: 600;
  margin-top: 12rpx;
}

.btn.primary {
  background: #2563eb;
  color: #fff;
}

.btn.outline {
  border: 1px solid #2563eb;
  color: #2563eb;
  background: #fff;
}

.message {
  display: block;
  margin-top: 12rpx;
  color: #dc2626;
  font-size: 24rpx;
}

.empty {
  color: #5b6b7a;
  text-align: center;
  padding: 40rpx 0;
}

.question-card {
  border: 1px solid #dde3e8;
  border-radius: 12rpx;
  padding: 20rpx;
  margin-bottom: 16rpx;
}

.badge {
  background: #e8f0fe;
  color: #2563eb;
  border-radius: 999rpx;
  padding: 4rpx 14rpx;
  font-size: 22rpx;
}

.badge.teal {
  background: #d9f3ef;
  color: #0f766e;
}

.stem {
  display: block;
  margin: 14rpx 0;
  font-size: 28rpx;
  line-height: 1.6;
}

.options {
  display: flex;
  flex-direction: column;
  gap: 10rpx;
}

.option {
  border: 1px solid #dde3e8;
  border-radius: 12rpx;
  padding: 12rpx 16rpx;
  font-size: 24rpx;
}

.analysis {
  display: block;
  margin-top: 12rpx;
  color: #0f766e;
  font-size: 24rpx;
}

.link {
  display: inline-block;
  margin-top: 10rpx;
  color: #2563eb;
  font-size: 24rpx;
}

.action-link {
  color: #2563eb;
  font-size: 24rpx;
  padding: 4rpx 8rpx;
}

.action-link.favorited {
  color: #dc2626;
}

.delete-link {
  color: #dc2626;
  font-size: 24rpx;
  padding: 4rpx 8rpx;
}
</style>
