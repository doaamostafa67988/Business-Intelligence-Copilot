import { ChatInterface } from '@/components/ChatInterface'
import { Sidebar } from '@/components/Sidebar'

export default function HomePage() {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 flex flex-col overflow-hidden">
        <ChatInterface />
      </main>
    </div>
  )
}
