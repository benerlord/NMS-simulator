<script setup lang="ts">
import { ref } from 'vue'

import { apiGet } from '@/api/http'

interface Health {
  status: string
}

const health = ref<Health | null>(null)
const loading = ref(false)

async function probe() {
  loading.value = true
  try {
    health.value = await apiGet<Health>('/health')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <a-card title="仪表盘">
    <a-space direction="vertical">
      <a-typography-text>M1 脚手架占位页。</a-typography-text>
      <a-space>
        <a-button type="primary" :loading="loading" @click="probe">
          探测 /admin/api/health
        </a-button>
        <a-tag v-if="health" color="green">status: {{ health.status }}</a-tag>
      </a-space>
    </a-space>
  </a-card>
</template>
