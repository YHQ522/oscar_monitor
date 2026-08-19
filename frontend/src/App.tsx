import { lazy, Suspense, useEffect } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Spin } from 'antd'
import { useAuth } from './store/auth'
import Layout from './components/Layout'
import type { ReactNode } from 'react'

// 路由级懒加载：按需分包，减小首屏体积
const LoginPage = lazy(() => import('./pages/LoginPage'))
const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const ServersPage = lazy(() => import('./pages/ServersPage'))
const ServerAddPage = lazy(() => import('./pages/ServerAddPage'))
const ServerDetailPage = lazy(() => import('./pages/ServerDetailPage'))
const LogHistoryPage = lazy(() => import('./pages/LogHistoryPage'))
const ControlPage = lazy(() => import('./pages/ControlPage'))
const UsersPage = lazy(() => import('./pages/UsersPage'))
const ConfigPage = lazy(() => import('./pages/ConfigPage'))
const ReportsPage = lazy(() => import('./pages/ReportsPage'))
const SqlTerminalPage = lazy(() => import('./pages/SqlTerminalPage'))
const ProfilePage = lazy(() => import('./pages/ProfilePage'))

function RequireAuth({ children }: { children: ReactNode }) {
  const { token, ready, fetchUser } = useAuth()
  useEffect(() => {
    if (token && !ready) {
      fetchUser()
    }
  }, [token, ready, fetchUser])

  if (!token) {
    return <Navigate to="/login" replace />
  }
  if (!ready) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spin size="large" />
      </div>
    )
  }
  return <>{children}</>
}

function RequirePerm({ perm, children }: { perm?: string; children: ReactNode }) {
  const user = useAuth((s) => s.user)
  if (!user) return null
  const ok = user.is_admin || (perm ? user.perms.includes(perm) : true)
  if (!ok) {
    return <Navigate to="/" replace />
  }
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      {/* 全局 Suspense：覆盖整个路由树，lazy 页面加载时统一显示 loading */}
      <Suspense fallback={<div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}><Spin size="large" /></div>}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/"
            element={
              <RequireAuth>
                <Layout />
              </RequireAuth>
            }
          >
            <Route index element={<RequirePerm perm="dashboard"><DashboardPage /></RequirePerm>} />
            <Route path="servers" element={<RequirePerm perm="servers_view"><ServersPage /></RequirePerm>} />
            <Route path="servers/add" element={<RequirePerm perm="servers_edit"><ServerAddPage /></RequirePerm>} />
            <Route path="server/:id" element={<RequirePerm perm="servers_view"><ServerDetailPage /></RequirePerm>} />
            <Route path="server/:id/log-history" element={<RequirePerm perm="servers_view"><LogHistoryPage /></RequirePerm>} />
            <Route path="control" element={<RequirePerm perm="control_view"><ControlPage /></RequirePerm>} />
            <Route path="users" element={<RequirePerm perm="admin"><UsersPage /></RequirePerm>} />
            <Route path="config" element={<RequirePerm perm="admin"><ConfigPage /></RequirePerm>} />
            <Route path="reports" element={<RequirePerm perm="reports_view"><ReportsPage /></RequirePerm>} />
            <Route path="sql-terminal" element={<RequirePerm perm="sql_terminal"><SqlTerminalPage /></RequirePerm>} />
            <Route path="profile" element={<ProfilePage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </Suspense>
    </BrowserRouter>
  )
}
