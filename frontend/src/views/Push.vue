<template>
  <div v-loading="loading">
    <h2>🔔 定时推送</h2>

    <el-row :gutter="20">
      <el-col :xs="24" :md="14">
        <el-card shadow="hover" style="margin-bottom: 20px">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span>推送订阅列表</span>
              <el-button type="primary" size="small" @click="openCreate">+ 新建订阅</el-button>
            </div>
          </template>
          <el-empty v-if="!subscriptions.length" description="暂无订阅" :image-size="60" />
          <el-table v-else :data="subscriptions" stripe>
            <el-table-column prop="name" label="名称" min-width="120" show-overflow-tooltip />
            <el-table-column prop="method" label="方式" width="100">
              <template #default="{ row }">
                <el-tag size="small">{{ methodLabel(row.method) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="strategy" label="策略" width="100">
              <template #default="{ row }">
                <el-tag size="small" type="info">{{ strategyLabel(row.strategy) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="200" align="center">
              <template #default="{ row }">
                <el-button size="small" type="success" :loading="testingId === row.id" @click="onTestPush(row)">测试</el-button>
                <el-button size="small" type="danger" @click="onDelete(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-card shadow="hover">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span>推送历史</span>
              <el-button size="small" @click="loadHistory">刷新</el-button>
            </div>
          </template>
          <el-empty v-if="!history.length" description="暂无推送记录" :image-size="60" />
          <el-timeline v-else>
            <el-timeline-item
              v-for="h in history"
              :key="h.id"
              :timestamp="h.sent_at || h.created_at || h.time"
              :type="h.success === false ? 'danger' : 'success'"
            >
              <div>
                <strong>{{ h.subscription_name || h.name || '推送' }}</strong>
                <el-tag size="small" :type="h.success === false ? 'danger' : 'success'" style="margin-left: 8px;">
                  {{ h.success === false ? '失败' : '成功' }}
                </el-tag>
              </div>
              <div v-if="h.message" style="color:#606266; margin-top: 4px; font-size: 12px;">{{ h.message }}</div>
            </el-timeline-item>
          </el-timeline>
        </el-card>
      </el-col>

      <el-col :xs="24" :md="10">
        <el-card shadow="hover">
          <template #header>创建订阅</template>
          <el-form :model="form" label-width="90px">
            <el-form-item label="名称" required>
              <el-input v-model="form.name" placeholder="订阅名称" />
            </el-form-item>
            <el-form-item label="推送方式">
              <el-select v-model="form.method" style="width: 100%">
                <el-option label="邮件" value="email" />
                <el-option label="Webhook" value="webhook" />
                <el-option label="企业微信" value="wechat_work" />
                <el-option label="钉钉" value="dingtalk" />
                <el-option label="飞书" value="feishu" />
                <el-option label="Telegram" value="telegram" />
              </el-select>
            </el-form-item>
            <el-form-item label="推送策略">
              <el-select v-model="form.strategy" style="width: 100%">
                <el-option label="热门" value="trending" />
                <el-option label="最新" value="latest" />
                <el-option label="推荐" value="recommended" />
                <el-option label="每日精选" value="daily_pick" />
              </el-select>
            </el-form-item>
            <el-form-item label="配置">
              <el-input
                v-model="form.configStr"
                type="textarea"
                :rows="6"
                placeholder='JSON 配置，例如：&#10;{"to": "user@example.com"}&#10;或 {"webhook_url": "https://..."}'
              />
              <div style="color:#909399; font-size: 12px;">请输入合法的 JSON</div>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="creating" @click="onCreate">创建订阅</el-button>
              <el-button @click="resetForm">重置</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getPushSubscriptions, createPushSubscription, deletePushSubscription,
  getPushHistory, testPush,
} from '../api'

const loading = ref(false)
const creating = ref(false)
const testingId = ref(-1)
const subscriptions = ref([])
const history = ref([])

const form = reactive({
  name: '',
  method: 'email',
  strategy: 'trending',
  configStr: '{\n  "to": ""\n}',
})

const methodLabel = (m) => ({
  email: '邮件', webhook: 'Webhook', wechat_work: '企业微信',
  dingtalk: '钉钉', feishu: '飞书', telegram: 'Telegram',
}[m] || m)

const strategyLabel = (s) => ({
  trending: '热门', latest: '最新', recommended: '推荐', daily_pick: '每日精选',
}[s] || s)

const loadSubscriptions = async () => {
  loading.value = true
  try {
    const { data } = await getPushSubscriptions()
    subscriptions.value = Array.isArray(data) ? data : (data.subscriptions || [])
  } catch (e) {
    ElMessage.error('加载订阅失败')
  } finally {
    loading.value = false
  }
}

const loadHistory = async () => {
  try {
    const { data } = await getPushHistory()
    history.value = Array.isArray(data) ? data : (data.history || [])
  } catch (e) {
    ElMessage.error('加载历史失败')
  }
}

const openCreate = () => {
  resetForm()
}

const resetForm = () => {
  form.name = ''
  form.method = 'email'
  form.strategy = 'trending'
  form.configStr = '{\n  "to": ""\n}'
}

const onCreate = async () => {
  if (!form.name.trim()) {
    ElMessage.warning('请输入订阅名称')
    return
  }
  let config = {}
  try {
    config = JSON.parse(form.configStr)
  } catch (e) {
    ElMessage.error('配置 JSON 格式错误')
    return
  }
  creating.value = true
  try {
    await createPushSubscription(form.name, form.method, config, form.strategy)
    ElMessage.success('订阅创建成功')
    resetForm()
    loadSubscriptions()
  } catch (e) {
    ElMessage.error('创建失败：' + (e.message || '未知错误'))
  } finally {
    creating.value = false
  }
}

const onDelete = (row) => {
  ElMessageBox.confirm(`确定删除订阅「${row.name}」？`, '提示', { type: 'warning' })
    .then(async () => {
      try {
        await deletePushSubscription(row.id)
        ElMessage.success('已删除')
        loadSubscriptions()
      } catch (e) {
        ElMessage.error('删除失败')
      }
    })
    .catch(() => {})
}

const onTestPush = async (row) => {
  testingId.value = row.id
  try {
    await testPush(row.id)
    ElMessage.success('测试推送已发送')
    loadHistory()
  } catch (e) {
    ElMessage.error('测试失败：' + (e.message || '未知错误'))
  } finally {
    testingId.value = -1
  }
}

onMounted(() => {
  loadSubscriptions()
  loadHistory()
})
</script>
