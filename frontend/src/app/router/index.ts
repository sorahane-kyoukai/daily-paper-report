import { createRouter, createWebHistory } from 'vue-router'

// Import pages
import HomePage from '@/pages/HomePage.vue'
import ArchivePage from '@/pages/ArchivePage.vue'
import ReportsPage from '@/pages/ReportsPage.vue'
import SourcesPage from '@/pages/SourcesPage.vue'
import StatusPage from '@/pages/StatusPage.vue'

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomePage,
    },
    {
      // Handle /index.html route (GitHub Pages default)
      path: '/index.html',
      redirect: '/',
    },
    {
      path: '/archive.html',
      redirect: '/archive',
    },
    {
      path: '/reports.html',
      redirect: '/reports',
    },
    {
      path: '/sources.html',
      redirect: '/sources',
    },
    {
      path: '/status.html',
      redirect: '/status',
    },
    {
      path: '/day/:date',
      name: 'day',
      component: HomePage,
    },
    {
      // Handle /day/:date.html routes (static file access)
      path: '/day/:date.html',
      redirect: (to) => ({ name: 'day', params: { date: to.params.date } }),
    },
    {
      path: '/archive',
      name: 'archive',
      component: ArchivePage,
    },
    {
      path: '/reports',
      name: 'reports',
      component: ReportsPage,
    },
    {
      path: '/reports/:type/:period',
      name: 'report-detail',
      component: ReportsPage,
    },
    {
      path: '/reports/:type/:period.html',
      redirect: (to) => ({
        name: 'report-detail',
        params: { type: to.params.type, period: to.params.period },
      }),
    },
    {
      path: '/sources',
      name: 'sources',
      component: SourcesPage,
    },
    {
      path: '/status',
      name: 'status',
      component: StatusPage,
    },
  ],
})

export default router
