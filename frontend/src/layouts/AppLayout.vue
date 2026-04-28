<script setup lang="ts">
import { computed } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'
import {
  ApartmentOutlined,
  ApiOutlined,
  AppstoreOutlined,
  KeyOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'

import { menuItems } from '@/router'

const route = useRoute()
const router = useRouter()

const iconMap = {
  ApartmentOutlined,
  AppstoreOutlined,
  ApiOutlined,
  KeyOutlined,
  SettingOutlined,
} as const

const selectedKeys = computed<string[]>(() => {
  const match = menuItems.find((item) => route.path.startsWith(item.path))
  return match ? [match.key] : []
})

const title = computed(() => {
  const matched = [...route.matched].reverse().find((m) => m.meta?.title)
  return (matched?.meta?.title as string | undefined) ?? ''
})

function onMenuClick({ key }: { key: string }) {
  const item = menuItems.find((m) => m.key === key)
  if (item) router.push(item.path)
}
</script>

<template>
  <a-layout class="app-layout">
    <a-layout-sider collapsible breakpoint="lg" theme="dark">
      <div class="brand">网管接口模拟</div>
      <a-menu
        theme="dark"
        mode="inline"
        :selected-keys="selectedKeys"
        @click="onMenuClick"
      >
        <a-menu-item v-for="item in menuItems" :key="item.key">
          <template #icon>
            <component :is="iconMap[item.icon]" />
          </template>
          <span>{{ item.label }}</span>
        </a-menu-item>
      </a-menu>
    </a-layout-sider>

    <a-layout>
      <a-layout-header class="app-header">
        <span class="page-title">{{ title }}</span>
      </a-layout-header>
      <a-layout-content class="app-content">
        <RouterView />
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>

<style scoped>
.app-layout {
  min-height: 100vh;
}

.brand {
  height: 48px;
  line-height: 48px;
  color: #fff;
  font-weight: 600;
  text-align: center;
  letter-spacing: 2px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.app-header {
  background: #fff;
  padding: 0 24px;
  border-bottom: 1px solid #f0f0f0;
}

.page-title {
  font-size: 16px;
  font-weight: 500;
}

.app-content {
  padding: 16px 24px;
  background: #f5f5f5;
}
</style>
