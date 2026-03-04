import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Agents from './pages/Agents'
import Tasks from './pages/Tasks'
import Revenue from './pages/Revenue'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="revenue" element={<Revenue />} />
        <Route path="agents" element={<Agents />} />
        <Route path="tasks" element={<Tasks />} />
      </Route>
    </Routes>
  )
}
