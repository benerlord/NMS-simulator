import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import AppLayout from '@/layouts/AppLayout.vue'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: AppLayout,
    children: [
      {
        path: '',
        name: 'dashboard',
        component: () => import('@/views/DashboardView.vue'),
        meta: { title: '仪表盘' },
      },
      {
        path: 'topologies',
        name: 'topologies',
        component: () => import('@/views/TopologiesView.vue'),
        meta: { title: '拓扑' },
      },
      {
        path: 'topologies/:id/canvas',
        name: 'canvas',
        component: () => import('@/views/CanvasView.vue'),
        meta: { title: '拓扑画布' },
      },
      {
        path: 'types',
        name: 'types',
        component: () => import('@/views/TypesView.vue'),
        meta: { title: '类型管理' },
      },
      {
        path: 'apis',
        name: 'apis',
        component: () => import('@/views/ApisView.vue'),
        meta: { title: '接口' },
      },
      {
        path: 'tokens',
        name: 'tokens',
        component: () => import('@/views/TokensView.vue'),
        meta: { title: 'Token' },
      },
      {
        path: 'logs',
        name: 'logs',
        component: () => import('@/views/LogsView.vue'),
        meta: { title: '请求日志' },
      },
      {
        path: 'settings',
        name: 'settings',
        component: () => import('@/views/SettingsView.vue'),
        meta: { title: '系统设置' },
      },
    ],
  },
]

export const menuItems = [
  { key: 'dashboard', path: '/',            label: '仪表盘',    icon: 'DashboardOutlined' },
  { key: 'topologies', path: '/topologies', label: '拓扑',      icon: 'ApartmentOutlined' },
  { key: 'types',     path: '/types',       label: '类型管理',  icon: 'AppstoreOutlined' },
  { key: 'apis',      path: '/apis',        label: '接口',      icon: 'ApiOutlined' },
  { key: 'tokens',    path: '/tokens',      label: 'Token',     icon: 'KeyOutlined' },
  { key: 'logs',      path: '/logs',        label: '请求日志',  icon: 'FileTextOutlined' },
  { key: 'settings',  path: '/settings',    label: '系统设置',  icon: 'SettingOutlined' },
] as const

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
