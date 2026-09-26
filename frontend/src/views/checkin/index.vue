<template>
  <section class="page" data-module="checkin">
    <header class="page-head">
      <div>
        <h2>出车检查管理</h2>
        <p class="page-desc">维护检查记录，围绕检查编号、检查车辆、检查日期、轮胎状况做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记检查记录</button>
        <button class="btn" type="button" @click="exportRows">导出出车检查清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="loading">
          <td :colspan="columns.length + 1" class="empty-state">正在加载出车检查记录…</td>
        </tr>
        <tr v-else-if="listError">
          <td :colspan="columns.length + 1" class="empty-state">
            <span class="error-text">列表加载失败：{{ listError }}</span>
            <button class="link retry-link" type="button" @click="reload">重试</button>
          </td>
        </tr>
        <template v-else>
          <tr v-for="row in rows" :key="String(row.id)">
            <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
            <td class="row-actions">
              <button class="link" type="button" @click="openDetail(row)">详情</button>
              <button
                v-for="action in rowActions(row)"
                :key="action"
                class="link"
                type="button"
                :disabled="actionPending"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
            </td>
          </tr>
          <tr v-if="!rows.length">
            <td :colspan="columns.length + 1" class="empty-state">
              <template v-if="activeFilters.length">
                当前过滤条件（{{ activeFilters.join('，') }}）下暂无待检查车辆，可
                <button class="link" type="button" @click="resetFilters">重置条件</button>
                后重新查询
              </template>
              <template v-else>
                暂无待检查车辆：当前没有需要出车检查的车辆，可点击右上角「登记检查记录」新增
              </template>
            </td>
          </tr>
        </template>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条出车检查记录</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 检查记录详情：动作权限与列表行、检查弹窗共用后端同一份判断 -->
    <div v-if="detailEntry" class="modal-mask" @click.self="closeDetail">
      <div class="modal-card">
        <header class="modal-head">
          <h3>检查记录详情</h3>
          <button class="link" type="button" @click="closeDetail">关闭</button>
        </header>
        <dl class="detail-grid">
          <template v-for="field in detailFields" :key="field">
            <dt>{{ field }}</dt>
            <dd>{{ detailEntry[field] ?? '—' }}</dd>
          </template>
        </dl>
        <p v-if="detailEntry['结论说明']" class="modal-hint">{{ detailEntry['结论说明'] }}</p>
        <footer class="modal-foot">
          <button
            v-for="action in rowActions(detailEntry)"
            :key="action"
            class="btn"
            type="button"
            :disabled="actionPending"
            @click="runAction(action, detailEntry)"
          >
            {{ action }}
          </button>
        </footer>
      </div>
    </div>

    <!-- 执行检查弹窗：填写并提交检查结论，失败保留内容并给出原因与重试入口 -->
    <form v-if="checkTarget" class="modal-mask form-mask" @submit.prevent="submitConclusion" @click.self="closeCheck">
      <div class="modal-card">
        <header class="modal-head">
          <h3>执行检查 · {{ checkTarget['检查编号'] }}</h3>
          <button class="link" type="button" @click="closeCheck">关闭</button>
        </header>
        <p class="modal-hint">检查车辆：{{ checkTarget['检查车辆'] }}｜检查日期：{{ checkTarget['检查日期'] }}</p>
        <label v-for="field in conclusionFields" :key="field" class="modal-field">
          <span>{{ field }}<em>*</em></span>
          <input v-model="checkForm[field]" :placeholder="field === '制冷运转' ? '必填，如：运转正常' : `请填写${field}`" />
        </label>
        <label class="modal-field">
          <span>检查结论<em>*</em></span>
          <select v-model="checkForm['检查结论']">
            <option value="" disabled>请选择检查结论</option>
            <option value="合格">合格</option>
            <option value="需整改">需整改</option>
          </select>
        </label>
        <p v-if="checkError" class="error-text modal-error">
          提交失败：{{ checkError }}
          <button class="link retry-link" type="button" :disabled="submitting" @click="submitConclusion">重试</button>
        </p>
        <footer class="modal-foot">
          <button class="btn primary" type="submit" :disabled="submitting">
            {{ submitting ? '提交中…' : '提交检查结论' }}
          </button>
        </footer>
      </div>
    </form>

    <!-- 登记检查记录弹窗：同一检查编号重复提交只生效一次 -->
    <form v-if="createOpen" class="modal-mask form-mask" @submit.prevent="submitCreate" @click.self="closeCreate">
      <div class="modal-card">
        <header class="modal-head">
          <h3>登记检查记录</h3>
          <button class="link" type="button" @click="closeCreate">关闭</button>
        </header>
        <label v-for="field in requiredFields" :key="field" class="modal-field">
          <span>{{ field }}<em>*</em></span>
          <input v-model="createForm[field]" :placeholder="`请填写${field}`" />
        </label>
        <p v-if="createError" class="error-text modal-error">
          登记失败：{{ createError }}
          <button class="link retry-link" type="button" :disabled="creating" @click="submitCreate">重试</button>
        </p>
        <footer class="modal-foot">
          <button class="btn primary" type="submit" :disabled="creating">
            {{ creating ? '提交中…' : '提交登记' }}
          </button>
        </footer>
      </div>
    </form>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { extractError, parseAction, request } from '@/api/client'

type Row = Record<string, any>

const ENDPOINT = '/api/checkin'
const columns = ["检查编号", "检查车辆", "检查日期", "轮胎状况", "制冷运转", "厢体密封", "检查人员", "检查状态"]
const detailFields = ["检查编号", "检查车辆", "检查日期", "轮胎状况", "制冷运转", "厢体密封", "检查人员", "检查结论", "检查状态"]
const filterFields = ["检查编号", "检查车辆", "检查日期"]
const requiredFields = ["检查编号", "检查车辆", "检查日期"]
const conclusionFields = ["轮胎状况", "制冷运转", "厢体密封", "检查人员"]
const filterParamMap: Record<string, string> = { 检查编号: 'keyword', 检查车辆: 'vehicle', 检查日期: 'date' }

const rows = ref<Row[]>([])
const total = ref(0)
const loading = ref(false)
const listError = ref('')
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = ref<Record<string, string>>({})
const stats = ref<{ label: string; value: number }[]>([
  { label: '待检查车辆', value: 0 },
  { label: '整改中车辆', value: 0 },
  { label: '已通过车辆', value: 0 },
])
const actionPending = ref(false)

const detailEntry = ref<Row | null>(null)
const checkTarget = ref<Row | null>(null)
const checkForm = ref<Record<string, string>>({})
const checkError = ref('')
const submitting = ref(false)

const createOpen = ref(false)
const createForm = ref<Record<string, string>>({})
const createError = ref('')
const creating = ref(false)

const activeFilters = computed(() =>
  filterFields
    .filter((field) => (filters.value[field] ?? '').trim())
    .map((field) => `${field}「${filters.value[field].trim()}」`),
)

function rowActions(row: Row | null): string[] {
  const actions = row?.['可执行动作']
  return Array.isArray(actions) ? actions : []
}

function buildQuery(): string {
  const params = new URLSearchParams()
  for (const field of filterFields) {
    const value = (filters.value[field] ?? '').trim()
    if (value) params.set(filterParamMap[field], value)
  }
  return params.toString()
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  const query = buildQuery()
  window.open(`${ENDPOINT}/export${query ? `?${query}` : ''}`, '_blank')
}

async function reload() {
  loading.value = true
  listError.value = ''
  try {
    const response = await request(`${ENDPOINT}?${buildQuery()}`)
    if (!response.ok) {
      throw new Error(await extractError(response, '检查记录列表读取失败'))
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    // 失败时不把列表渲染成空态，避免和「真的没有数据」混淆
    rows.value = []
    total.value = 0
    listError.value = error instanceof Error ? error.message : '出车检查列表读取失败'
  } finally {
    loading.value = false
  }
}

async function loadSummary() {
  try {
    const response = await request(`${ENDPOINT}/summary`)
    if (!response.ok) return
    const payload = await response.json()
    const byStatus = payload.by_status ?? {}
    stats.value = [
      { label: '待检查车辆', value: byStatus['待检查'] ?? 0 },
      { label: '整改中车辆', value: byStatus['整改中'] ?? 0 },
      { label: '已通过车辆', value: byStatus['已通过'] ?? 0 },
    ]
  } catch {
    /* 统计卡片失败不阻塞列表主体 */
  }
}

async function refresh() {
  await Promise.all([reload(), loadSummary()])
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error(await extractError(response, '检查记录详情读取失败'))
    }
    detailEntry.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '检查记录详情读取失败'
  }
}

function closeDetail() {
  detailEntry.value = null
}

function openCheck(row: Row) {
  detailEntry.value = null
  checkTarget.value = row
  checkForm.value = {
    轮胎状况: String(row['轮胎状况'] ?? ''),
    制冷运转: String(row['制冷运转'] ?? ''),
    厢体密封: String(row['厢体密封'] ?? ''),
    检查人员: String(row['检查人员'] ?? ''),
    检查结论: '',
  }
  checkError.value = ''
}

function closeCheck() {
  checkTarget.value = null
}

async function submitConclusion() {
  const target = checkTarget.value
  if (!target || submitting.value) return
  submitting.value = true
  checkError.value = ''
  try {
    const response = await request(`${ENDPOINT}/${target.id}/conclusion`, {
      method: 'POST',
      body: JSON.stringify({ values: checkForm.value }),
    })
    const payload = await parseAction(response, '检查结论提交失败，请稍后重试')
    // 成功（含幂等的重复提交）后整表重拉，不会在列表里重复插入同一条检查编号
    noticeMessage.value = payload.message ?? '检查结论已提交'
    checkTarget.value = null
    await refresh()
  } catch (error) {
    // 保留已填内容，给出后端原因；用户可直接点「重试」
    checkError.value = error instanceof Error ? error.message : '检查结论提交失败，请稍后重试'
  } finally {
    submitting.value = false
  }
}

function openCreate() {
  createForm.value = { 检查编号: '', 检查车辆: '', 检查日期: '' }
  createError.value = ''
  createOpen.value = true
}

function closeCreate() {
  createOpen.value = false
}

async function submitCreate() {
  if (creating.value) return
  creating.value = true
  createError.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: createForm.value }),
    })
    const payload = await parseAction(response, '检查记录登记失败，请稍后重试')
    noticeMessage.value = payload.message ?? '检查记录已登记'
    createOpen.value = false
    await refresh()
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '检查记录登记失败，请稍后重试'
  } finally {
    creating.value = false
  }
}

async function runAction(action: string, row: Row) {
  if (action === '执行检查') {
    openCheck(row)
    return
  }
  errorMessage.value = ''
  noticeMessage.value = ''
  actionPending.value = true
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await parseAction(response, '出车检查动作未生效，请稍后重试')
    noticeMessage.value = payload.message ?? '操作已完成'
    if (payload.entry && detailEntry.value && String(detailEntry.value.id) === String(row.id)) {
      detailEntry.value = payload.entry
    }
    await refresh()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '出车检查操作失败'
  } finally {
    actionPending.value = false
  }
}

onMounted(refresh)
</script>

<style scoped>
.modal-mask {
  position: fixed;
  inset: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(15, 23, 42, 0.45);
}
.form-mask {
  margin: 0;
}
.modal-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 440px;
  max-width: calc(100vw - 40px);
  max-height: calc(100vh - 60px);
  padding: 16px 20px;
  overflow: auto;
  background: #fff;
  border-radius: 10px;
}
.modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.modal-head h3 {
  margin: 0;
  font-size: 15px;
}
.modal-hint {
  margin: 0;
  font-size: 12px;
  color: var(--muted);
}
.modal-field span {
  display: block;
  margin-bottom: 4px;
  font-size: 12px;
  color: var(--muted);
}
.modal-field em {
  margin-left: 2px;
  font-style: normal;
  color: #b42318;
}
.modal-field input,
.modal-field select {
  width: 100%;
  padding: 6px 8px;
  font-size: 13px;
  border: 1px solid var(--border);
  border-radius: 6px;
}
.modal-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.modal-error {
  margin: 0;
  font-size: 12px;
}
.detail-grid {
  display: grid;
  grid-template-columns: 88px 1fr;
  gap: 6px 12px;
  margin: 0;
  font-size: 13px;
}
.detail-grid dt {
  color: var(--muted);
}
.detail-grid dd {
  margin: 0;
}
.retry-link {
  margin-left: 8px;
}
.btn:disabled,
.link:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
