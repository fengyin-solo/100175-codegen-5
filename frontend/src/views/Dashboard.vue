<template>
  <section class="page">
    <header class="page-head">
      <div>
        <h2>运营概览</h2>
        <p class="page-desc">汇总各业务模块的关键指标，先看总量再看异常。</p>
      </div>
    </header>
    <div class="stat-row">
      <article v-for="card in cards" :key="card.label" class="stat-card">
        <span class="stat-label">{{ card.label }}</span>
        <strong class="stat-value">{{ card.value }}</strong>
      </article>
    </div>

    <h3 style="margin:16px 0 8px">能源用电总量（与能源计量台账、点位详情同源）</h3>
    <table v-if="energyPointRows.length" class="data-table">
      <thead>
        <tr><th>计量点位</th><th>峰段(kWh)</th><th>平段(kWh)</th><th>谷段(kWh)</th><th>用电总量(kWh)</th><th>台账条数</th><th>未采集</th></tr>
      </thead>
      <tbody>
        <tr v-for="row in energyPointRows" :key="row.point_id">
          <td>{{ row.point_name }}</td>
          <td>{{ formatNumber(row.usage_by_period['峰']) }}</td>
          <td>{{ formatNumber(row.usage_by_period['平']) }}</td>
          <td>{{ formatNumber(row.usage_by_period['谷']) }}</td>
          <td><strong>{{ formatNumber(row.total) }}</strong></td>
          <td>{{ row.record_count }}</td>
          <td>{{ row.missing_count }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else class="empty-state">能源计量台账暂无数据，请到能源计量台账补录</p>

    <h3 style="margin:16px 0 8px">各业务模块</h3>
    <table class="data-table">
      <thead>
        <tr><th>业务模块</th><th>今日新增</th><th>待处理</th><th>异常量</th></tr>
      </thead>
      <tbody>
        <tr v-for="row in moduleRows" :key="row.name">
          <td>{{ row.name }}</td>
          <td>{{ row.created }}</td>
          <td>{{ row.pending }}</td>
          <td>{{ row.abnormal }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchJson } from '@/api/client'

type Overview = {
  cards: { label: string; value: number }[]
  modules: { name: string; created: number; pending: number; abnormal: number }[]
  energy: EnergyOverview | null
}

type PeriodName = '峰' | '平' | '谷'
type EnergyOverview = {
  total: number
  record_count: number
  point_summaries: {
    point_id: number
    point_name: string
    usage_by_period: Record<PeriodName, number>
    total: number
    record_count: number
    missing_count: number
  }[]
}

const cards = ref<Overview['cards']>([])
const moduleRows = ref<Overview['modules']>([])
const energyPointRows = ref<EnergyOverview['point_summaries']>([])

function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

onMounted(async () => {
  try {
    const payload = await fetchJson<Overview>('/api/overview')
    cards.value = payload.cards
    moduleRows.value = payload.modules
    // 首页用电总量直接取后端统一聚合，和台账页、点位详情是同一份结果
    energyPointRows.value = payload.energy?.point_summaries ?? []
  } catch {
    cards.value = [{"label": "业务模块", "value": 0}, {"label": "今日新增", "value": 0}]
    moduleRows.value = []
    energyPointRows.value = []
  }
})
</script>
