<template>
  <div v-loading="loading">
    <h2>📤 批量导入</h2>

    <el-tabs v-model="activeTab" type="card">
      <el-tab-pane label="标题批量导入" name="titles">
        <el-card shadow="hover">
          <el-form :model="titleForm" label-width="100px">
            <el-form-item label="数据源">
              <el-radio-group v-model="titleForm.source">
                <el-radio label="oa">OpenAlex</el-radio>
                <el-radio label="arxiv">arXiv</el-radio>
                <el-radio label="crossref">Crossref</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="标题列表">
              <el-input
                v-model="titleForm.text"
                type="textarea"
                :rows="12"
                placeholder="每行一个论文标题，例如：&#10;Attention Is All You Need&#10;BERT: Pre-training of Deep Bidirectional Transformers"
              />
              <div style="color:#909399; font-size: 12px; margin-top: 4px;">
                已输入 {{ titleCount }} 个标题
              </div>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="importing" @click="onImportByTitles">开始导入</el-button>
              <el-button @click="titleForm.text = ''">清空</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="多主题导入" name="topics">
        <el-row :gutter="20">
          <el-col :xs="24" :md="14">
            <el-card shadow="hover" v-loading="topicsLoading">
              <template #header>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                  <span>主题库</span>
                  <el-button size="small" @click="loadTopics">刷新</el-button>
                </div>
              </template>
              <el-empty v-if="!topicsLoading && !topicCategories.length" description="暂无主题" />
              <el-collapse v-model="activeTopicGroups">
                <el-collapse-item
                  v-for="group in topicCategories"
                  :key="group.category || group.name"
                  :title="`${group.category || group.name} (${(group.topics || group.items || []).length})`"
                  :name="group.category || group.name"
                >
                  <el-checkbox-group v-model="selectedTopics">
                    <el-checkbox
                      v-for="topic in (group.topics || group.items || [])"
                      :key="topic"
                      :label="topic"
                      style="display: block; margin: 4px 0;"
                    >
                      {{ topic }}
                    </el-checkbox>
                  </el-checkbox-group>
                </el-collapse-item>
              </el-collapse>
            </el-card>
          </el-col>
          <el-col :xs="24" :md="10">
            <el-card shadow="hover">
              <template #header>导入设置</template>
              <el-form :model="topicForm" label-width="100px">
                <el-form-item label="数据源">
                  <el-checkbox-group v-model="topicForm.sources">
                    <el-checkbox label="oa">OpenAlex</el-checkbox>
                    <el-checkbox label="arxiv">arXiv</el-checkbox>
                  </el-checkbox-group>
                </el-form-item>
                <el-form-item label="每主题数量">
                  <el-input-number v-model="topicForm.perTopic" :min="1" :max="200" />
                </el-form-item>
                <el-form-item label="已选主题">
                  <div>{{ selectedTopics.length }} 个</div>
                </el-form-item>
                <el-form-item>
                  <el-button type="primary" :loading="importing" :disabled="!selectedTopics.length" @click="onImportTopics">
                    开始批量导入
                  </el-button>
                  <el-button @click="selectedTopics = []">清空选择</el-button>
                </el-form-item>
              </el-form>
            </el-card>
          </el-col>
        </el-row>
      </el-tab-pane>
    </el-tabs>

    <el-card v-if="progress.visible" shadow="hover" style="margin-top: 20px;">
      <template #header>导入进度</template>
      <el-progress :percentage="progress.percentage" :status="progress.status" />
      <div style="margin-top: 12px; color: #606266;">
        {{ progress.message }}
      </div>
      <div v-if="progress.result" style="margin-top: 12px;">
        <el-alert :title="`成功导入 ${progress.result.success || 0} / ${progress.result.total || 0} 篇`" type="success" :closable="false" />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { batchImportByTitles, getTopicLibrary, runBatchImport } from '../api'

const loading = ref(false)
const importing = ref(false)
const activeTab = ref('titles')

const titleForm = reactive({
  text: '',
  source: 'oa',
})

const titleCount = computed(() => {
  return titleForm.text.split('\n').map(s => s.trim()).filter(Boolean).length
})

const progress = reactive({
  visible: false,
  percentage: 0,
  message: '',
  status: '',
  result: null,
})

const onImportByTitles = async () => {
  const titles = titleForm.text.split('\n').map(s => s.trim()).filter(Boolean)
  if (!titles.length) {
    ElMessage.warning('请输入至少一个标题')
    return
  }
  importing.value = true
  progress.visible = true
  progress.percentage = 30
  progress.message = `正在导入 ${titles.length} 篇论文...`
  progress.status = ''
  progress.result = null
  try {
    const { data } = await batchImportByTitles(titles, titleForm.source)
    progress.percentage = 100
    progress.status = 'success'
    progress.message = '导入完成'
    progress.result = data
    ElMessage.success('批量导入完成')
  } catch (e) {
    progress.percentage = 100
    progress.status = 'exception'
    progress.message = '导入失败：' + (e.message || '未知错误')
    ElMessage.error('导入失败：' + (e.message || '未知错误'))
  } finally {
    importing.value = false
  }
}

const topicsLoading = ref(false)
const topicCategories = ref([])
const activeTopicGroups = ref([])
const selectedTopics = ref([])
const topicForm = reactive({
  sources: ['oa'],
  perTopic: 20,
})

const loadTopics = async () => {
  topicsLoading.value = true
  try {
    const { data } = await getTopicLibrary()
    let arr
    if (Array.isArray(data)) {
      // 后端返回数组格式：[{category, topics}, ...]
      arr = data
    } else if (data && typeof data === 'object') {
      // 后端返回字典格式：{"人工智能": [...], "量子计算": [...]}
      // 转换为 [{category, topics}, ...]
      arr = Object.entries(data).map(([category, topics]) => ({ category, topics }))
    } else {
      arr = []
    }
    topicCategories.value = arr
    if (arr.length) activeTopicGroups.value = arr.map(g => g.category || g.name).slice(0, 3)
  } catch (e) {
    ElMessage.error('加载主题库失败')
  } finally {
    topicsLoading.value = false
  }
}

const onImportTopics = async () => {
  if (!selectedTopics.value.length) {
    ElMessage.warning('请选择至少一个主题')
    return
  }
  if (!topicForm.sources.length) {
    ElMessage.warning('请至少选择一个数据源')
    return
  }
  importing.value = true
  progress.visible = true
  progress.percentage = 30
  progress.message = `正在导入 ${selectedTopics.value.length} 个主题，每主题 ${topicForm.perTopic} 篇...`
  progress.status = ''
  progress.result = null
  try {
    const { data } = await runBatchImport(selectedTopics.value, topicForm.perTopic, topicForm.sources)
    progress.percentage = 100
    progress.status = 'success'
    progress.message = '批量导入完成'
    progress.result = data
    ElMessage.success('批量导入完成')
  } catch (e) {
    progress.percentage = 100
    progress.status = 'exception'
    progress.message = '导入失败：' + (e.message || '未知错误')
    ElMessage.error('导入失败：' + (e.message || '未知错误'))
  } finally {
    importing.value = false
  }
}

onMounted(loadTopics)
</script>
