<template>
  <section class="page" data-module="energy">
    <header class="page-head">
      <div>
        <h2>能源计量台账</h2>
        <p class="page-desc">
          登记各计量点位的用电量与峰谷时段；当前口径为第 {{ overview?.policy?.version ?? '-' }} 版（{{ policyText(overview?.policy) }}），
          口径调整后已补录数据按新口径重算，历史结果仍按当时口径保留。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="showBackfill = true">补录用能数据</button>
        <button class="btn" type="button" @click="showPolicy = !showPolicy">调整峰谷时段</button>
        <button class="btn ghost" type="button" @click="showHistory = !showHistory">历史口径结果</button>
      </div>
    </header>

    <!-- 用电总量：与首页、点位详情同一份 /api/energy/overview 结果 -->
    <div class="stat-row">
      <article v-for="card in (overview?.cards ?? [])" :key="card.label" class="stat-card">
        <span class="stat-label">{{ card.label }}</span>
        <strong class="stat-value">{{ formatUsage(card.value, card.label) }}</strong>
      </article>
    </div>

    <!-- 补录表单 -->
    <form v-if="showBackfill" class="filter-bar" @submit.prevent="submitBackfill">
      <label class="filter-item">
        <span>计量点位</span>
        <select v-model="backfill.point_code">
          <option value="" disabled>请选择点位</option>
          <option v-for="point in points" :key="point.id" :value="point.code">
            {{ point.code }} · {{ point.name }}（上限 {{ point.upper_limit }}）
          </option>
        </select>
      </label>
      <label class="filter-item">
        <span>计量日期</span>
        <input v-model="backfill.date" type="date" />
      </label>
      <label class="filter-item">
        <span>计量时间（HH:MM）</span>
        <input v-model="backfill.time" placeholder="如 10:30" />
      </label>
      <label class="filter-item">
        <span>用电量(kWh，留空=未采集)</span>
        <input v-model="backfill.usage" placeholder="采集器未回传可留空" />
      </label>
      <button class="btn primary" type="submit">提交补录</button>
      <button class="btn ghost" type="button" @click="showBackfill = false">收起</button>
      <p v-if="backfillMessage" :class="backfillOk ? 'page-desc' : 'error-text'" style="width:100%">
        {{ backfillMessage }}
      </p>
    </form>

    <!-- 峰谷口径调整 -->
    <section v-if="showPolicy" class="data-table" style="padding:12px;margin-bottom:12px">
      <h3 style="margin:0 0 8px">峰谷时段口径调整（未覆盖的时间自动归为平段，时间不可重叠）</h3>
      <div v-for="(group, gIndex) in policyDraft" :key="group.period" style="margin-bottom:8px">
        <strong>{{ group.period }}段：</strong>
          <template v-for="(range, rIndex) in group.ranges" :key="rIndex">
            <input v-model="range[0]" placeholder="HH:MM" style="width:80px" /> ~
            <input v-model="range[1]" placeholder="HH:MM" style="width:80px" />
            <button class="link" type="button" @click="removeRange(gIndex, rIndex)">删除区间</button>
          </template>
        <button class="btn" type="button" @click="addRange(gIndex)">+ 添加区间</button>
      </div>
      <div style="display:flex;gap:8px">
        <button class="btn primary" type="button" @click="submitPolicy">按新口径重算</button>
        <button class="btn ghost" type="button" @click="resetPolicyDraft">恢复当前口径</button>
      </div>
      <p v-if="policyMessage" :class="policyOk ? 'page-desc' : 'error-text'">{{ policyMessage }}</p>
    </section>

    <!-- 历史口径快照 -->
    <section v-if="showHistory" style="margin-bottom:12px">
      <h3 style="margin:0 0 8px">历史结果（按当时时段口径保留）</h3>
      <table v-if="snapshots.length" class="data-table">
        <thead>
          <tr><th>口径版本</th><th>时段划分</th><th>归档时间</th><th>当时用电总量(kWh)</th><th>台账条数</th></tr>
        </thead>
        <tbody>
          <tr v-for="snapshot in snapshots" :key="snapshot.id">
            <td>第 {{ snapshot.policy_version }} 版</td>
            <td>{{ snapshotPeriodText(snapshot.periods) }}</td>
            <td>{{ snapshot.archived_at }}</td>
            <td>{{ snapshotTotal(snapshot) }}</td>
            <td>{{ snapshotCard(snapshot, '台账条数') }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="empty-state">尚未调整过峰谷口径，暂无历史快照</p>
    </section>

    <!-- 各点位峰谷用量与总量 -->
    <table v-if="(overview?.point_summaries ?? []).length" class="data-table">
      <thead>
        <tr>
          <th>点位编号</th><th>点位名称</th><th>安装位置</th>
          <th>峰段用量(kWh)</th><th>平段用量(kWh)</th><th>谷段用量(kWh)</th>
          <th>用电总量(kWh)</th><th>台账条数</th><th>未采集</th><th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in overview?.point_summaries ?? []" :key="row.point_id">
          <td>{{ row.point_code }}</td>
          <td>{{ row.point_name }}</td>
          <td>{{ row.location }}</td>
          <td>{{ formatNumber(row.usage_by_period['峰']) }}</td>
          <td>{{ formatNumber(row.usage_by_period['平']) }}</td>
          <td>{{ formatNumber(row.usage_by_period['谷']) }}</td>
          <td><strong>{{ formatNumber(row.total) }}</strong></td>
          <td>{{ row.record_count }}</td>
          <td>{{ row.missing_count }}</td>
          <td><button class="link" type="button" @click="openDetail(row.point_id)">查看分组明细</button></td>
        </tr>
      </tbody>
    </table>
    <p v-else-if="loaded" class="empty-state">尚未建立计量点位，暂无台账数据</p>

    <!-- 点位详情：按峰谷时段分组 -->
    <section v-if="detail" style="margin-top:16px">
      <div class="page-head">
        <div>
          <h3 style="margin:0">{{ detail.point_code }} · {{ detail.point_name }} 点位用量明细</h3>
          <p class="page-desc">
            按峰谷时段分组排列；峰 {{ formatNumber(detail.usage_by_period['峰']) }} /
            平 {{ formatNumber(detail.usage_by_period['平']) }} /
            谷 {{ formatNumber(detail.usage_by_period['谷']) }}，
            合计 <strong>{{ formatNumber(detail.total) }}</strong> kWh（未采集 {{ detail.missing_count }} 条不计入）
          </p>
        </div>
        <button class="btn ghost" type="button" @click="detail = null">关闭明细</button>
      </div>
      <template v-for="group in detail.groups" :key="group.period">
        <h4 style="margin:12px 0 4px">{{ group.period }}段 · 用量 {{ formatNumber(group.usage) }} kWh · {{ group.count }} 条</h4>
        <table class="data-table">
          <thead>
            <tr><th>日期</th><th>时间</th><th>用电量(kWh)</th><th>归属口径版本</th></tr>
          </thead>
          <tbody>
            <tr v-for="record in group.records" :key="record.id">
              <td>{{ record.date }}</td>
              <td>{{ record.time }}</td>
              <!-- 没采集到数据显示空态，绝不把 null 渲染成 0 -->
              <td>{{ record.usage === null || record.usage === undefined ? '未采集' : formatNumber(record.usage) }}</td>
              <td>v{{ record.policy_version }}</td>
            </tr>
            <tr v-if="!group.records.length">
              <td colspan="4" class="empty-state">{{ group.period }}段暂无补录记录</td>
            </tr>
          </tbody>
        </table>
      </template>
    </section>

    <footer class="page-foot">
      <span>共 {{ overview?.record_count ?? 0 }} 条补录，其中 {{ overview?.missing_count ?? 0 }} 条未采集到数据</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchJson, request } from '@/api/client'

type PeriodName = '峰' | '平' | '谷'
type PolicyPeriod = { period: '峰' | '谷'; ranges: [string, string][] }
type Overview = {
  policy: { version: number; updated_at: string; periods: PolicyPeriod[] } | null
  cards: { label: string; value: number | null }[]
  period_totals: Record<PeriodName, number>
  total: number
  record_count: number
  missing_count: number
  point_summaries: {
    point_id: number
    point_code: string
    point_name: string
    location: string
    upper_limit: number
    usage_by_period: Record<PeriodName, number>
    total: number
    record_count: number
    missing_count: number
  }[]
}
type Point = { id: number; code: string; name: string; location: string; upper_limit: number }
type Detail = {
  point_id: number
  point_code: string
  point_name: string
  location: string
  usage_by_period: Record<PeriodName, number>
  total: number
  missing_count: number
  groups: { period: PeriodName; count: number; usage: number; records: EnergyRecord[] }[]
}
type EnergyRecord = {
  id: number
  point_id: number
  date: string
  time: string
  usage: number | null
  policy_version: number
  period: PeriodName
}
type Snapshot = {
  id: number
  policy_version: number
  periods: PolicyPeriod[]
  archived_at: string
  cards: { label: string; value: number }[]
}

const overview = ref<Overview | null>(null)
const points = ref<Point[]>([])
const detail = ref<Detail | null>(null)
const snapshots = ref<Snapshot[]>([])
const loaded = ref(false)
const errorMessage = ref('')

const showBackfill = ref(false)
const backfill = ref({ point_code: '', date: '', time: '', usage: '' })
const backfillMessage = ref('')
const backfillOk = ref(true)

const showPolicy = ref(false)
const showHistory = ref(false)
const policyDraft = ref<{ period: '峰' | '谷'; ranges: [string, string][] }[]>([])
const policyMessage = ref('')
const policyOk = ref(true)

function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function formatUsage(value: number | null, label: string): string {
  if (label.includes('条数')) return String(value ?? 0)
  return formatNumber(value)
}

function policyText(policy: Overview['policy'] | undefined): string {
  if (!policy) return '—'
  return snapshotPeriodText(policy.periods)
}

function snapshotPeriodText(periods: PolicyPeriod[]): string {
  const parts = periods.map((item) => {
    const ranges = item.ranges.map(([start, end]) => `${start}-${end}`).join('、')
    return `${item.period}(${ranges})`
  })
  return `${parts.join('，')}，其余为平段`
}

function snapshotTotal(snapshot: Snapshot): string {
  const card = snapshot.cards?.find((item) => item.label === '用电总量(kWh)')
  return formatNumber(card?.value ?? 0)
}

function snapshotCard(snapshot: Snapshot, label: string): number {
  return snapshot.cards?.find((item) => item.label === label)?.value ?? 0
}

async function reload() {
  errorMessage.value = ''
  try {
    const [overviewPayload, pointsPayload] = await Promise.all([
      fetchJson<Overview>('/api/energy/overview'),
      fetchJson<{ items: Point[] }>('/api/energy/points'),
    ])
    overview.value = overviewPayload
    points.value = pointsPayload.items ?? []
    loaded.value = true
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '能源台账数据读取失败'
  }
}

async function submitBackfill() {
  backfillMessage.value = ''
  const payload: Record<string, unknown> = {
    point_code: backfill.value.point_code,
    date: backfill.value.date,
    time: backfill.value.time,
  }
  if (backfill.value.usage.trim() !== '') {
    payload.usage = Number(backfill.value.usage)
  }
  try {
    const response = await request('/api/energy/records', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    const result = await response.json()
    backfillOk.value = Boolean(result.ok)
    backfillMessage.value = result.message || (result.ok ? '补录已登记' : '补录被拦下')
    if (result.ok) {
      backfill.value = { point_code: '', date: '', time: '', usage: '' }
      await reload()
      if (detail.value) await openDetail(detail.value.point_id)
    }
  } catch (error) {
    backfillOk.value = false
    backfillMessage.value = error instanceof Error ? error.message : '补录提交失败'
  }
}

function draftFromCurrent() {
  const current = overview.value?.policy?.periods ?? []
  policyDraft.value = current.map((item) => ({
    period: item.period,
    ranges: item.ranges.map((range) => [range[0], range[1]] as [string, string]),
  }))
  if (!policyDraft.value.some((item) => item.period === '峰')) {
    policyDraft.value.unshift({ period: '峰', ranges: [['08:00', '12:00']] })
  }
  if (!policyDraft.value.some((item) => item.period === '谷')) {
    policyDraft.value.push({ period: '谷', ranges: [['23:00', '07:00']] })
  }
}

function resetPolicyDraft() {
  draftFromCurrent()
  policyMessage.value = ''
}

function addRange(groupIndex: number) {
  policyDraft.value[groupIndex].ranges.push(['', ''])
}

function removeRange(groupIndex: number, rangeIndex: number) {
  policyDraft.value[groupIndex].ranges.splice(rangeIndex, 1)
}

async function submitPolicy() {
  policyMessage.value = ''
  try {
    const response = await request('/api/energy/policy', {
      method: 'PUT',
      body: JSON.stringify({
        periods: policyDraft.value.map((group) => ({
          period: group.period,
          ranges: group.ranges.filter(([start, end]) => start.trim() && end.trim()),
        })),
      }),
    })
    const result = await response.json()
    policyOk.value = Boolean(result.ok)
    policyMessage.value = result.message || '口径调整失败'
    if (result.ok) {
      await reload()
      draftFromCurrent()
      await reloadSnapshots()
      if (detail.value) await openDetail(detail.value.point_id)
    }
  } catch (error) {
    policyOk.value = false
    policyMessage.value = error instanceof Error ? error.message : '口径调整失败'
  }
}

async function openDetail(pointId: number) {
  try {
    detail.value = await fetchJson<Detail>(`/api/energy/points/${pointId}`)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '点位详情读取失败'
  }
}

async function reloadSnapshots() {
  try {
    const payload = await fetchJson<{ items: Snapshot[] }>('/api/energy/snapshots')
    snapshots.value = payload.items ?? []
  } catch {
    snapshots.value = []
  }
}

onMounted(async () => {
  await reload()
  draftFromCurrent()
  await reloadSnapshots()
})
</script>
