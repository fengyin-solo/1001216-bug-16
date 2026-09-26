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
      <article v-for="item in statCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>检查编号</span>
        <input v-model="filters.keyword" placeholder="按检查编号检索" />
      </label>
      <label class="filter-item">
        <span>检查车辆</span>
        <input v-model="filters.vehicle" placeholder="按检查车辆检索" />
      </label>
      <label class="filter-item">
        <span>检查状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>检查判断</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="loading">
          <td :colspan="columns.length + 2" class="empty-state">检查记录加载中…</td>
        </tr>
        <tr v-else-if="loadError">
          <td :colspan="columns.length + 2" class="empty-state error-state-cell">
            <p class="state-title">检查记录加载失败</p>
            <p class="state-desc">{{ loadError }}</p>
            <p class="state-desc">请确认后端服务可用后重试，当前过滤条件已保留。</p>
            <button class="btn primary" type="button" @click="reload">重新加载</button>
          </td>
        </tr>
        <tr v-else-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state empty-state-cell">
            <p class="state-title">{{ emptyTitle }}</p>
            <p class="state-desc">{{ emptyDesc }}</p>
            <div v-if="activeFilters.length" class="state-filters">
              <span v-for="item in activeFilters" :key="item.key" class="filter-chip">
                {{ item.label }}：{{ item.value }}
              </span>
            </div>
            <button v-if="activeFilters.length" class="btn" type="button" @click="resetFilters">清空过滤条件</button>
          </td>
        </tr>
        <template v-else>
          <tr v-for="row in rows" :key="String(row.id)">
            <td v-for="column in columns" :key="column">
              <button v-if="column === '检查编号'" class="link" type="button" @click="openDetail(row)">
                {{ row[column] ?? '—' }}
              </button>
              <span v-else-if="isCheckItem(column) && isBlank(row[column])" class="missing-text">未填写</span>
              <span v-else>{{ row[column] ?? '—' }}</span>
            </td>
            <td class="verdict-cell">
              <span class="tag" :class="verdictTagClass(row)">{{ status(row) }}</span>
              <span class="verdict-desc">{{ verdict(row).状态说明 }}</span>
            </td>
            <td class="row-actions">
              <button
                v-for="action in actions"
                :key="action"
                class="link"
                type="button"
                :disabled="!canRun(row, action)"
                :title="actionTitle(row, action)"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
              <button class="link" type="button" @click="openDetail(row)">详情</button>
            </td>
          </tr>
        </template>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条出车检查记录<span v-if="activeFilters.length">（已按当前条件过滤）</span></span>
      <span v-if="errorMessage" class="error-text">
        {{ errorMessage }}
        <button v-if="failedAction" class="link retry-link" type="button" @click="retryFailedAction">重试</button>
      </span>
    </footer>

    <!-- 执行检查弹窗 -->
    <div v-if="checkModal.open" class="modal-mask" @click.self="closeCheckModal">
      <div class="modal">
        <header class="modal-head">
          <h3>执行检查 · {{ checkModal.row?.['检查编号'] }}</h3>
          <button class="btn ghost" type="button" @click="closeCheckModal">关闭</button>
        </header>
        <div class="modal-body">
          <dl class="detail-grid">
            <div v-for="field in detailFields" :key="field" class="detail-item">
              <dt>{{ field }}</dt>
              <dd>
                <span v-if="isCheckItem(field) && isBlank(checkModal.row?.[field])" class="missing-text">
                  未填写
                </span>
                <span v-else>{{ checkModal.row?.[field] ?? '—' }}</span>
              </dd>
            </div>
          </dl>
          <p class="verdict-banner" :class="canCheckInModal ? '' : 'warn'">
            {{ checkModal.row ? checkModal.row['判定']?.状态说明 : '' }}
          </p>
          <label v-if="missingItemsInModal.length" class="form-item">
            <span class="missing-text">待补录检查项：{{ missingItemsInModal.join('、') }}</span>
            <span class="form-hint">制冷机组不运转也要填写具体原因（如“冷机故障停机”），不能留空。</span>
          </label>
          <label class="form-item">
            <span>检查结论 <em>*</em></span>
            <select v-model="checkModal.conclusion" :disabled="!canCheckInModal || checkModal.submitting">
              <option value="" disabled>请选择检查结论</option>
              <option value="合格">合格</option>
              <option value="不合格">不合格（转入整改）</option>
            </select>
          </label>
          <p v-if="checkModal.error" class="error-text submit-error">
            {{ checkModal.error }}
          </p>
        </div>
        <footer class="modal-foot">
          <button class="btn" type="button" :disabled="checkModal.submitting" @click="closeCheckModal">取消</button>
          <button
            v-if="checkModal.error"
            class="btn primary"
            type="button"
            :disabled="checkModal.submitting || !checkModal.conclusion"
            @click="submitCheck"
          >
            重试提交
          </button>
          <button
            v-else
            class="btn primary"
            type="button"
            :disabled="checkModal.submitting || !checkModal.conclusion"
            @click="submitCheck"
          >
            {{ checkModal.submitting ? '提交中…' : '提交检查结论' }}
          </button>
        </footer>
      </div>
    </div>

    <!-- 详情弹窗：判断口径与列表、检查弹窗完全一致（同一份判定数据） -->
    <div v-if="detailRow" class="modal-mask" @click.self="detailRow = null">
      <div class="modal">
        <header class="modal-head">
          <h3>检查记录详情 · {{ detailRow['检查编号'] }}</h3>
          <button class="btn ghost" type="button" @click="detailRow = null">关闭</button>
        </header>
        <div class="modal-body">
          <dl class="detail-grid">
            <div v-for="field in detailFields" :key="field" class="detail-item">
              <dt>{{ field }}</dt>
              <dd>
                <span v-if="isCheckItem(field) && isBlank(detailRow[field])" class="missing-text">未填写</span>
                <span v-else>{{ detailRow[field] ?? '—' }}</span>
              </dd>
            </div>
            <div class="detail-item">
              <dt>检查结论</dt>
              <dd>{{ detailRow['检查结论'] ?? '尚未提交' }}</dd>
            </div>
          </dl>
          <p class="verdict-banner" :class="verdict(detailRow).可执行动作.length ? '' : 'warn'">
            <span class="tag" :class="verdictTagClass(detailRow)">{{ status(detailRow) }}</span>
            {{ verdict(detailRow).状态说明 }}
          </p>
          <p v-if="verdict(detailRow).禁止原因" class="form-hint">不可提交原因：{{ verdict(detailRow).禁止原因 }}</p>
        </div>
        <footer class="modal-foot">
          <button class="btn" type="button" @click="detailRow = null">关闭</button>
          <button
            class="btn primary"
            type="button"
            :disabled="!canRun(detailRow, '执行检查')"
            :title="actionTitle(detailRow, '执行检查')"
            @click="fromDetailRunCheck"
          >
            执行检查
          </button>
        </footer>
      </div>
    </div>

    <!-- 登记弹窗 -->
    <div v-if="createModal.open" class="modal-mask" @click.self="closeCreate">
      <div class="modal">
        <header class="modal-head">
          <h3>登记检查记录</h3>
          <button class="btn ghost" type="button" @click="closeCreate">关闭</button>
        </header>
        <div class="modal-body">
          <label v-for="field in createFields" :key="field" class="form-item">
            <span>{{ field }} <em v-if="requiredCreateFields.includes(field)">*</em></span>
            <input v-model="createModal.form[field]" :placeholder="`请输入${field}`" />
          </label>
          <p v-if="createModal.error" class="error-text submit-error">{{ createModal.error }}</p>
        </div>
        <footer class="modal-foot">
          <button class="btn" type="button" :disabled="createModal.submitting" @click="closeCreate">取消</button>
          <button
            class="btn primary"
            type="button"
            :disabled="createModal.submitting"
            @click="submitCreate"
          >
            {{ createModal.submitting ? '提交中…' : (createModal.error ? '重试提交' : '提交登记') }}
          </button>
        </footer>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Verdict = {
  当前状态: string
  缺失检查项: string[]
  可执行动作: string[]
  不可执行动作: string[]
  禁止原因: string
  状态说明: string
}
type Row = {
  id: number
  判定: Verdict
  [key: string]: string | number | null | string[] | Verdict
}

const ENDPOINT = '/api/checkin'
const columns = ["检查编号", "检查车辆", "检查日期", "轮胎状况", "制冷运转", "厢体密封", "检查人员", "检查结论", "检查状态"]
const detailFields = ["检查编号", "检查车辆", "检查日期", "轮胎状况", "制冷运转", "厢体密封", "检查人员", "检查状态"]
const actions = ["执行检查", "登记整改", "复核通过"]
const statuses = ["待检查", "已检查", "整改中", "已通过"]
const checkItems = ["轮胎状况", "制冷运转", "厢体密封"]

const createFields = ["检查编号", "检查车辆", "检查日期", "轮胎状况", "制冷运转", "厢体密封", "检查人员"]
const requiredCreateFields = ["检查编号", "检查车辆", "检查日期"]

const rows = ref<Row[]>([])
const total = ref(0)
const loading = ref(false)
const loadError = ref('')
const errorMessage = ref('')
const failedAction = ref<{ action: string; row: Row } | null>(null)
// 过滤条件是独立状态：加载失败、空结果或动作提交后都不清空，保证重试仍在同一视图里
const filters = reactive<{ keyword: string; vehicle: string; status: string }>({
  keyword: '',
  vehicle: '',
  status: '',
})

const statCards = ref([
  { label: '待检查车辆', value: 0 },
  { label: '整改中车辆', value: 0 },
  { label: '已通过车辆', value: 0 },
])

const activeFilters = computed(() => {
  const items: { key: string; label: string; value: string }[] = []
  if (filters.keyword.trim()) items.push({ key: 'keyword', label: '检查编号', value: filters.keyword.trim() })
  if (filters.vehicle.trim()) items.push({ key: 'vehicle', label: '检查车辆', value: filters.vehicle.trim() })
  if (filters.status) items.push({ key: 'status', label: '检查状态', value: filters.status })
  return items
})

const pendingOnly = computed(() => {
  const hasTextFilter = Boolean(filters.keyword.trim() || filters.vehicle.trim())
  return filters.status === '待检查' || (!filters.status && !hasTextFilter)
})

const emptyTitle = computed(() =>
  pendingOnly.value ? '暂无待检查车辆' : '当前条件下暂无出车检查记录',
)
const emptyDesc = computed(() => {
  if (loadError.value) return ''
  if (activeFilters.value.length) return '按当前过滤条件没有匹配的记录，过滤条件已保留，可调整后重新查询。'
  return pendingOnly.value
    ? '所有车辆的出车检查都已处理完毕，或尚未有待检查车辆登记。'
    : '暂无检查记录，可点击右上角「登记检查记录」新建。'
})

function isCheckItem(field: string): boolean {
  return checkItems.includes(field)
}

function isBlank(value: unknown): boolean {
  return value === null || value === undefined || String(value).trim() === ''
}

function verdict(row: Row): Verdict {
  return row.判定 ?? {
    当前状态: String(row['检查状态'] ?? ''),
    缺失检查项: [],
    可执行动作: [],
    不可执行动作: actions,
    禁止原因: '缺少判断信息，请重新加载列表',
    状态说明: '判断信息缺失，请重新加载列表',
  }
}

function status(row: Row): string {
  return verdict(row).当前状态 || String(row['检查状态'] ?? '')
}

function canRun(row: Row, action: string): boolean {
  return verdict(row).可执行动作.includes(action)
}

function actionTitle(row: Row, action: string): string {
  if (canRun(row, action)) return action
  return verdict(row).禁止原因 || `当前状态不可${action}`
}

function verdictTagClass(row: Row): string {
  const s = status(row)
  if (s === '已通过') return 'tag-ok'
  if (s === '整改中') return 'tag-warn'
  if (s === '待检查' && verdict(row).缺失检查项.length) return 'tag-danger'
  if (s === '待检查') return 'tag-info'
  return ''
}

function resetFilters() {
  filters.keyword = ''
  filters.vehicle = ''
  filters.status = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

async function readErrorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const payload = await response.json()
    if (payload && typeof payload.detail === 'string') return payload.detail
    if (payload && typeof payload.message === 'string') return payload.message
  } catch {
    // 非 JSON 响应时退回通用文案
  }
  return `${fallback}（HTTP ${response.status}）`
}

async function reload() {
  loading.value = true
  loadError.value = ''
  errorMessage.value = ''
  const params = new URLSearchParams()
  if (filters.keyword.trim()) params.set('keyword', filters.keyword.trim())
  if (filters.vehicle.trim()) params.set('vehicle', filters.vehicle.trim())
  if (filters.status) params.set('status', filters.status)
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) {
      loadError.value = await readErrorMessage(response, '检查记录列表读取失败')
      return
    }
    const payload = await response.json()
    rows.value = (payload.items ?? []) as Row[]
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    // 网络层失败：与“真的没有数据”明确区分，保留过滤条件并给出重试入口
    loadError.value = error instanceof Error ? error.message : '出车检查列表读取失败'
  } finally {
    loading.value = false
  }
  void loadStats()
}

async function loadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (!response.ok) return
    const data = (await response.json()) as Record<string, number>
    statCards.value = [
      { label: '待检查车辆', value: data['待检查'] ?? 0 },
      { label: '整改中车辆', value: data['整改中'] ?? 0 },
      { label: '已通过车辆', value: data['已通过'] ?? 0 },
    ]
  } catch {
    // 统计卡片失败不阻塞列表，保持 0 不误导成“没有待检查车辆”的空态
  }
}

async function postAction(action: string, row: Row, extra: Record<string, string> = {}) {
  const response = await request(`${ENDPOINT}/${row.id}/actions`, {
    method: 'POST',
    body: JSON.stringify({ values: { action, ...extra } }),
  })
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, `${action}提交失败`))
  }
  const payload = (await response.json()) as { ok: boolean; message: string; entry: Row | null }
  if (!payload.ok) {
    // 业务失败：给出后端原因，并把重试入口留在页脚
    throw new Error(payload.message)
  }
  return payload
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  failedAction.value = null
  if (action === '执行检查') {
    openCheckModal(row)
    return
  }
  try {
    const result = await postAction(action, row)
    errorMessage.value = result.message
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : `${action}失败，请稍后重试`
    failedAction.value = { action, row }
  }
}

async function retryFailedAction() {
  if (!failedAction.value) return
  const { action, row } = failedAction.value
  errorMessage.value = ''
  failedAction.value = null
  try {
    const result = await postAction(action, row)
    errorMessage.value = result.message
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : `${action}失败，请稍后重试`
    failedAction.value = { action, row }
  }
}

// ---- 执行检查弹窗 ----

const checkModal = reactive<{
  open: boolean
  row: Row | null
  conclusion: string
  submitting: boolean
  error: string
}>({
  open: false,
  row: null,
  conclusion: '',
  submitting: false,
  error: '',
})

const canCheckInModal = computed(() =>
  checkModal.row ? verdict(checkModal.row).可执行动作.includes('执行检查') : false,
)

const missingItemsInModal = computed(() =>
  checkModal.row ? verdict(checkModal.row).缺失检查项 : [],
)

function openCheckModal(row: Row) {
  checkModal.open = true
  checkModal.row = row
  checkModal.conclusion = ''
  checkModal.submitting = false
  checkModal.error = ''
}

function closeCheckModal() {
  if (checkModal.submitting) return
  checkModal.open = false
  checkModal.row = null
  checkModal.error = ''
}

async function submitCheck() {
  if (!checkModal.row || !checkModal.conclusion || checkModal.submitting) return
  checkModal.submitting = true
  checkModal.error = ''
  try {
    const result = await postAction('执行检查', checkModal.row, {
      检查结论: checkModal.conclusion,
    })
    checkModal.open = false
    checkModal.row = null
    errorMessage.value = result.message
    await reload()
  } catch (error) {
    // 失败后按钮恢复可点，并在弹窗内直接给出原因与“重试提交”入口
    checkModal.error = error instanceof Error ? error.message : '检查结论提交失败，请稍后重试'
  } finally {
    checkModal.submitting = false
  }
}

// ---- 详情弹窗（与列表共用同一条 row.判定，口径天然一致） ----

const detailRow = ref<Row | null>(null)

async function openDetail(row: Row) {
  // 拉取最新明细；详情里的判定与列表来自同一个后端函数
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (response.ok) {
      detailRow.value = (await response.json()) as Row
      return
    }
    detailRow.value = row
  } catch {
    detailRow.value = row
  }
}

function fromDetailRunCheck() {
  if (!detailRow.value) return
  const row = detailRow.value
  detailRow.value = null
  openCheckModal(row)
}

// ---- 登记弹窗 ----

const createModal = reactive<{
  open: boolean
  form: Record<string, string>
  submitting: boolean
  error: string
}>({
  open: false,
  form: {},
  submitting: false,
  error: '',
})

function openCreate() {
  createModal.open = true
  createModal.form = Object.fromEntries(createFields.map((field) => [field, '']))
  createModal.submitting = false
  createModal.error = ''
}

function closeCreate() {
  if (createModal.submitting) return
  createModal.open = false
  createModal.error = ''
}

async function submitCreate() {
  if (createModal.submitting) return
  createModal.submitting = true
  createModal.error = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({
        values: Object.fromEntries(
          Object.entries(createModal.form).filter(([, value]) => value.trim() !== ''),
        ),
      }),
    })
    if (!response.ok) {
      throw new Error(await readErrorMessage(response, '检查记录登记失败'))
    }
    const payload = (await response.json()) as { ok: boolean; message: string }
    if (!payload.ok) throw new Error(payload.message)
    createModal.open = false
    errorMessage.value = payload.message
    await reload()
  } catch (error) {
    // 检查编号重复时后端返回 ok=true 的幂等提示；其它失败保留表单供重试
    createModal.error = error instanceof Error ? error.message : '检查记录登记失败，请稍后重试'
  } finally {
    createModal.submitting = false
  }
}

onMounted(reload)
</script>

<style scoped>
.state-title { margin: 0 0 4px; font-weight: 600; color: #1f2937; }
.state-desc { margin: 2px 0; color: var(--muted); font-size: 12px; }
.state-filters { display: flex; flex-wrap: wrap; gap: 6px; justify-content: center; margin: 8px 0; }
.filter-chip {
  background: #eef4ff;
  border: 1px solid #c7d9f7;
  color: #1f6feb;
  border-radius: 999px;
  padding: 2px 10px;
  font-size: 12px;
}
.empty-state-cell { padding: 28px 12px; }
.error-state-cell .state-title { color: #b42318; }
.error-state-cell .btn { margin-top: 8px; }

.verdict-cell { max-width: 260px; }
.verdict-desc { display: block; color: var(--muted); font-size: 12px; margin-top: 4px; }
.missing-text { color: #b42318; }
.retry-link { margin-left: 6px; font-size: 12px; }

.tag {
  display: inline-block;
  border-radius: 999px;
  padding: 1px 10px;
  font-size: 12px;
  border: 1px solid transparent;
}
.tag-ok { background: #e8f7ee; color: #1a7f37; border-color: #b7e4c7; }
.tag-warn { background: #fff4e5; color: #b54708; border-color: #f5d29b; }
.tag-danger { background: #fdeaea; color: #b42318; border-color: #f5b5b0; }
.tag-info { background: #eef4ff; color: #1f6feb; border-color: #c7d9f7; }

.row-actions .link:disabled { color: #9aa6b2; cursor: not-allowed; text-decoration: none; }

.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}
.modal {
  width: 560px;
  max-width: calc(100vw - 32px);
  max-height: calc(100vh - 48px);
  overflow-y: auto;
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.18);
}
.modal-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
}
.modal-head h3 { margin: 0; font-size: 15px; }
.modal-body { padding: 14px 16px; }
.modal-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid var(--border);
}

.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 16px; margin: 0 0 12px; }
.detail-item { display: flex; gap: 8px; font-size: 13px; margin: 0; }
.detail-item dt { color: var(--muted); min-width: 64px; }
.detail-item dd { margin: 0; }

.verdict-banner {
  margin: 8px 0;
  padding: 8px 10px;
  border-radius: 6px;
  background: #e8f7ee;
  color: #1a7f37;
  font-size: 13px;
}
.verdict-banner.warn { background: #fdeaea; color: #b42318; }
.verdict-banner .tag { margin-right: 6px; }

.form-item { display: flex; flex-direction: column; gap: 4px; margin-bottom: 10px; font-size: 13px; }
.form-item em { color: #b42318; font-style: normal; }
.form-item select,
.form-item input {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 13px;
}
.form-hint { color: var(--muted); font-size: 12px; margin: 2px 0; }
.submit-error { margin: 6px 0 0; }
</style>
