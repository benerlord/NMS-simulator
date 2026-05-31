import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import AppLayout from '@/layouts/AppLayout.vue'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: AppLayout,
    redirect: '/topologies',
    children: [
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
        path: 'mock-instances',
        name: 'mockInstances',
        component: () => import('@/views/MockInstancesView.vue'),
        meta: { title: '实例管理' },
      },
      {
        path: 'domains',
        name: 'domains',
        component: () => import('@/views/DomainsView.vue'),
        meta: { title: '网管/设备管理' },
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
  { key: 'topologies', path: '/topologies', label: '拓扑',      icon: 'ApartmentOutlined' },
  { key: 'types',     path: '/types',       label: '类型管理',  icon: 'AppstoreOutlined' },
  { key: 'apis',      path: '/apis',        label: '接口',      icon: 'ApiOutlined' },
  { key: 'mockInstances', path: '/mock-instances', label: '实例管理', icon: 'ApiOutlined' },
  { key: 'domains',   path: '/domains',     label: '网管/设备管理', icon: 'ClusterOutlined' },
  { key: 'tokens',    path: '/tokens',      label: 'Token',     icon: 'KeyOutlined' },
  { key: 'settings',  path: '/settings',    label: '系统设置',  icon: 'SettingOutlined' },
] as const

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
