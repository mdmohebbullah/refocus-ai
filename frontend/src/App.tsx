import { Navigate, Route, Routes } from 'react-router-dom'
import { useApp } from './state/app'
import { Layout } from './components/Layout'
import { Spinner } from './components/ui'
import { LoginPage } from './pages/Login'
import { DashboardPage } from './pages/Dashboard'
import { ProjectsPage, ProjectPage } from './pages/Projects'
import { EditorPage } from './pages/Editor'
import { ResumePage } from './pages/Resume'
import { CheckpointsPage } from './pages/Checkpoints'
import { ThoughtsPage } from './pages/Thoughts'
import { TabsPage } from './pages/Tabs'
import { ActivityPage } from './pages/Activity'
import { HistoryPage } from './pages/History'
import { NotesPage } from './pages/Notes'
import { AssistantPage } from './pages/Assistant'
import { SearchPage } from './pages/Search'
import { SettingsPage } from './pages/Settings'

export function App() {
  const { me, loading } = useApp()
  if (loading) return <Spinner label="Opening Re-Focus AI" />
  if (!me) return <Routes><Route path="*" element={<LoginPage />} /></Routes>
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/projects/:id" element={<ProjectPage />} />
        <Route path="/documents/:id" element={<EditorPage />} />
        <Route path="/tabs" element={<TabsPage />} />
        <Route path="/activity" element={<ActivityPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/checkpoints" element={<CheckpointsPage />} />
        <Route path="/thoughts" element={<ThoughtsPage />} />
        <Route path="/resume" element={<ResumePage />} />
        <Route path="/notes" element={<NotesPage />} />
        <Route path="/assistant" element={<AssistantPage />} />
        <Route path="/search" element={<SearchPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </Layout>
  )
}
