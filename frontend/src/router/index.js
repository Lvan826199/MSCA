import { createRouter, createWebHashHistory } from "vue-router"

const routes = [
  {
    path: "/",
    name: "Home",
    component: () => import("@/views/HomeView.vue"),
  },
  {
    path: "/mirror",
    name: "Mirror",
    component: () => import("@/views/MirrorView.vue"),
  },
  {
    path: "/settings",
    name: "Settings",
    component: () => import("@/views/SettingsView.vue"),
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

export default router
