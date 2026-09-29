<template>
  <section class="page" data-module="energy">
    <header class="page-head">
      <div>
        <h2>能源计量台账</h2>
        <p class="page-desc">登记各计量点位的用电量与峰谷时段，按峰谷口径呈现各点位用量与总量；口径调整后补录数据按新口径重算，历史结果按当时口径保留。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openRecord">补录数据</button>
        <button class="btn" type="button" @click="openStandard">调整峰谷口径</button>
        <button class="btn" type="button" @click="recompute">重新重算</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="card in statCards" :key="card.label" class="stat-card">
        <span class="stat-label">{{ card.label }}</span>
        <strong class="stat-value">{{ card.value }}</strong>
      </article>
    </div>
    <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>

    <h3 class="section-title">各点位峰谷用量与总量</h3>
    <table class="data-table">
      <thead>
        <tr>
          <th>点位编号</th><th>点位名称</th><th>计量上限(kWh)</th>
          <th>峰电量(kWh)</th><th>谷电量(kWh)</th><th>平电量(kWh)</th>
          <th>总电量(kWh)</th><th>记录数</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="p in pointResults" :key="p.point_id">
          <td>{{ p.点位编号 }}</td>
          <td>{{ p.点位名称 }}</td>
          <td>{{ p.计量上限 }}</td>
          <td><template v-if="p.有数据">{{ p.峰电量 }}</template><span v-else class="empty-hint">暂无采集数据</span></td>
          <td><template v-if="p.有数据">{{ p.谷电量 }}</template><span v-else class="empty-hint">暂无采集数据</span></td>
          <td><template v-if="p.有数据">{{ p.平电量 }}</template><span v-else class="empty-hint">暂无采集数据</span></td>
          <td><template v-if="p.有数据">{{ p.总电量 }}</template><span v-else class="empty-hint">暂无采集数据</span></td>
          <td>{{ p.记录数 }}</td>
        </tr>
        <tr v-if="!pointResults.length">
          <td colspan="8" class="empty-state">暂无计量点位，可先登记点位</td>
        </tr>
      </tbody>
    </table>

    <h3 class="section-title">补录记录（按峰谷时段分组）</h3>
    <div v-for="group in groupedRecords" :key="group.period" class="period-group">
      <div class="period-head">
        <span class="period-tag" :class="`tag-${group.period}`">{{ group.period }}时段</span>
        <span class="period-subtotal">小计：{{ group.电量 }} kWh · {{ group.items.length }} 条</span>
      </div>
      <table class="data-table">
        <thead>
          <tr><th>登记时间</th><th>点位</th><th>采集日期</th><th>时段</th><th>电量(kWh)</th><th>峰电量</th><th>谷电量</th><th>平电量</th></tr>
        </thead>
        <tbody>
          <tr v-for="r in group.items" :key="r.id">
            <td>{{ r.登记时间 }}</td>
            <td>{{ pointName(r.point_id) }}</td>
            <td>{{ r.采集日期 }}</td>
            <td>{{ r.时段 }}</td>
            <td>{{ r.电量 }}</td>
            <td>{{ r.峰电量 }}</td>
            <td>{{ r.谷电量 }}</td>
            <td>{{ r.平电量 }}</td>
          </tr>
          <tr v-if="!group.items.length">
            <td colspan="8" class="empty-state">暂无{{ group.period }}段采集数据</td>
          </tr>
        </tbody>
      </table>
    </div>

    <h3 class="section-title">历史结果（按当时时段口径保留）</h3>
    <div v-for="snap in snapshots" :key="snap.id" class="snapshot-card">
      <div class="snapshot-head">
        <strong>口径 v{{ snap.口径版本 }}</strong>
        <span>{{ snap.重算时间 }}</span>
        <span>{{ snap.触发 }}</span>
      </div>
      <table class="data-table">
        <thead>
          <tr><th>点位编号</th><th>点位名称</th><th>峰电量(kWh)</th><th>谷电量(kWh)</th><th>平电量(kWh)</th><th>总电量(kWh)</th><th>记录数</th></tr>
        </thead>
        <tbody>
          <tr v-for="p in snap.结果" :key="p.point_id">
            <td>{{ p.点位编号 }}</td>
            <td>{{ p.点位名称 }}</td>
            <td><template v-if="p.有数据">{{ p.峰电量 }}</template><span v-else class="empty-hint">暂无采集数据</span></td>
            <td><template v-if="p.有数据">{{ p.谷电量 }}</template><span v-else class="empty-hint">暂无采集数据</span></td>
            <td><template v-if="p.有数据">{{ p.平电量 }}</template><span v-else class="empty-hint">暂无采集数据</span></td>
            <td><template v-if="p.有数据">{{ p.总电量 }}</template><span v-else class="empty-hint">暂无采集数据</span></td>
            <td>{{ p.记录数 }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="recordDialog" class="modal-mask" @click.self="recordDialog = false">
      <div class="modal">
        <h3>补录用电量</h3>
        <form @submit.prevent="submitRecord">
          <label class="form-item">计量点位
            <select v-model="recordForm.point_id">
              <option v-for="p in points" :key="p.id" :value="p.id">{{ p.点位编号 }} {{ p.点位名称 }}</option>
            </select>
          </label>
          <label class="form-item">用电量(kWh)
            <input v-model="recordForm.电量" type="number" step="0.01" placeholder="不超过该点位计量上限" />
          </label>
          <label class="form-item">采集日期
            <input v-model="recordForm.采集日期" type="date" />
          </label>
          <label class="form-item">时段(HH:MM-HH:MM)
            <input v-model="recordForm.时段" placeholder="如 10:00-12:00" />
          </label>
          <div class="modal-actions">
            <button class="btn primary" type="submit">提交补录</button>
            <button class="btn ghost" type="button" @click="recordDialog = false">取消</button>
          </div>
        </form>
      </div>
    </div>

    <div v-if="standardDialog" class="modal-mask" @click.self="standardDialog = false">
      <div class="modal">
        <h3>调整峰谷时段口径</h3>
        <p class="form-hint">每行一个时段区间（HH:MM-HH:MM，可跨日如 22:00-06:00），其余时间视为平段。调整后补录数据按新口径重算，历史结果保留。</p>
        <form @submit.prevent="submitStandard">
          <label class="form-item">峰时段
            <textarea v-model="standardForm.峰时段" rows="3" placeholder="08:00-12:00&#10;18:00-22:00"></textarea>
          </label>
          <label class="form-item">谷时段
            <textarea v-model="standardForm.谷时段" rows="3" placeholder="00:00-06:00"></textarea>
          </label>
          <label class="form-item">调整说明
            <input v-model="standardForm.调整说明" placeholder="如：夏季峰谷时段调整" />
          </label>
          <div class="modal-actions">
            <button class="btn primary" type="submit">调整并重算</button>
            <button class="btn ghost" type="button" @click="standardDialog = false">取消</button>
          </div>
        </form>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Point = Record<string, any>
type RecordRow = Record<string, any>
type Snapshot = Record<string, any>

const ENDPOINT = '/api/energy'

const points = ref<Point[]>([])
const pointResults = ref<Point[]>([])
const records = ref<RecordRow[]>([])
const snapshots = ref<Snapshot[]>([])
const summary = ref<Record<string, any>>({})
const errorMessage = ref('')

const recordDialog = ref(false)
const standardDialog = ref(false)
const recordForm = ref<Record<string, any>>({ point_id: null, 电量: '', 采集日期: '', 时段: '' })
const standardForm = ref<Record<string, any>>({ 峰时段: '', 谷时段: '', 调整说明: '' })

const statCards = computed(() => [
  { label: '用电总量(kWh)', value: summary.value.总电量 ?? '—' },
  { label: '峰电量(kWh)', value: summary.value.峰电量 ?? '—' },
  { label: '谷电量(kWh)', value: summary.value.谷电量 ?? '—' },
  { label: '平电量(kWh)', value: summary.value.平电量 ?? '—' },
  { label: '台账条数', value: summary.value.台账条数 ?? '—' },
  { label: '点位/已采集', value: `${summary.value.采集点位数 ?? 0}/${summary.value.点位数 ?? 0}` },
  { label: '当前口径', value: summary.value.口径版本 ? `v${summary.value.口径版本}` : '—' },
])

const groupedRecords = computed(() => {
  const groups = ['峰', '谷', '平'].map((period) => {
    const items = records.value
      .filter((r) => r.时段分类 === period)
      .sort((a, b) => String(b.登记时间).localeCompare(String(a.登记时间)))
    const 电量 = items.reduce((sum, r) => sum + Number(r.电量 || 0), 0)
    return { period, items, 电量: Math.round(电量 * 100) / 100 }
  })
  return groups
})

function pointName(pointId: number): string {
  const point = points.value.find((p) => p.id === pointId)
  return point ? `${point.点位编号} ${point.点位名称}` : `点位${pointId}`
}

async function reload() {
  errorMessage.value = ''
  try {
    const [overviewRes, pointsRes, recordsRes, snapshotsRes] = await Promise.all([
      request(`${ENDPOINT}/overview`),
      request(`${ENDPOINT}/points`),
      request(`${ENDPOINT}/records?size=200`),
      request(`${ENDPOINT}/snapshots`),
    ])
    if (!overviewRes.ok) throw new Error('能源计量总览读取失败')
    if (!pointsRes.ok) throw new Error('计量点位读取失败')
    if (!recordsRes.ok) throw new Error('补录记录读取失败')
    if (!snapshotsRes.ok) throw new Error('历史结果读取失败')
    const overview = await overviewRes.json()
    pointResults.value = overview.点位结果 ?? []
    summary.value = overview.汇总 ?? {}
    const pointsPayload = await pointsRes.json()
    points.value = pointsPayload.items ?? []
    const recordsPayload = await recordsRes.json()
    records.value = recordsPayload.items ?? []
    const snapshotsPayload = await snapshotsRes.json()
    snapshots.value = snapshotsPayload.items ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '能源计量台账读取失败'
  }
}

function openRecord() {
  recordForm.value = { point_id: points.value[0]?.id ?? null, 电量: '', 采集日期: '', 时段: '' }
  recordDialog.value = true
}

function openStandard() {
  standardForm.value = { 峰时段: '', 谷时段: '', 调整说明: '' }
  standardDialog.value = true
}

async function submitRecord() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/records`, {
      method: 'POST',
      body: JSON.stringify({ values: { ...recordForm.value } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      errorMessage.value = payload.message || '补录失败'
      return
    }
    recordDialog.value = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '补录失败'
  }
}

async function submitStandard() {
  errorMessage.value = ''
  try {
    const 峰时段 = standardForm.value.峰时段.split('\n').map((s: string) => s.trim()).filter(Boolean)
    const 谷时段 = standardForm.value.谷时段.split('\n').map((s: string) => s.trim()).filter(Boolean)
    const response = await request(`${ENDPOINT}/standards`, {
      method: 'POST',
      body: JSON.stringify({ values: { 峰时段, 谷时段, 调整说明: standardForm.value.调整说明 } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      errorMessage.value = payload.message || '口径调整失败'
      return
    }
    standardDialog.value = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '口径调整失败'
  }
}

async function recompute() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/recompute`, { method: 'POST' })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      errorMessage.value = payload.message || '重算失败'
      return
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '重算失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.section-title { margin: 18px 0 8px; font-size: 15px; }
.period-group { margin-bottom: 14px; }
.period-head { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.period-tag { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 12px; color: #fff; }
.tag-峰 { background: #dc2626; }
.tag-谷 { background: #2563eb; }
.tag-平 { background: #64748b; }
.period-subtotal { font-size: 12px; color: var(--muted); }
.empty-hint { color: var(--muted); font-size: 12px; }
.snapshot-card { margin-bottom: 14px; border: 1px solid var(--border); border-radius: 8px; padding: 8px; background: #fff; }
.snapshot-head { display: flex; gap: 12px; align-items: baseline; margin-bottom: 6px; font-size: 13px; }
.modal-mask { position: fixed; inset: 0; background: rgba(15, 23, 42, 0.45); display: flex; align-items: center; justify-content: center; z-index: 50; }
.modal { background: #fff; border-radius: 10px; padding: 18px 20px; width: 460px; max-width: 92vw; }
.modal h3 { margin: 0 0 12px; }
.form-item { display: flex; flex-direction: column; gap: 4px; margin-bottom: 10px; font-size: 13px; }
.form-item input, .form-item select, .form-item textarea { border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; font-size: 13px; font-family: inherit; }
.form-hint { font-size: 12px; color: var(--muted); margin: 0 0 10px; }
.modal-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 4px; }
</style>
