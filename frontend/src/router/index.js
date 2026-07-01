import { createRouter, createWebHashHistory } from "vue-router"
import LogsView from "@/views/LogsView.vue"

const routes = [
  {
    path: "/",
    name: "Home",
    component: () => import("@/views/HomeView.vue"),
  },
  {
    path: "/mirror",
    name: "Mirror",
    component: { name: "MirrorRoutePlaceholder", render: () => null },
  },
  {
    path: "/logs",
    name: "Logs",
    component: LogsView,
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
