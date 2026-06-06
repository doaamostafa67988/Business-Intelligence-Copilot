import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Message, AppState, ChatResponse } from '@/types/api'

// Simple id generator (no uuid dependency needed)
function genId(): string {
  return Math.random().toString(36).slice(2) + Date.now().toString(36)
}

interface Actions {
  setSessionId: (id: string) => void
  addMessage: (msg: Omit<Message, 'id' | 'timestamp'>) => Message
  updateLastAssistantMessage: (response: ChatResponse) => void
  setLoading: (loading: boolean) => void
  setError: (error: string | null) => void
  clearSession: () => void
}

export const useStore = create<AppState & Actions>()(
  persist(
    (set, get) => ({
      sessionId: null,
      messages: [],
      isLoading: false,
      error: null,

      setSessionId: (id: string) => set({ sessionId: id }),

      addMessage: (msg: Omit<Message, 'id' | 'timestamp'>): Message => {
        const full: Message = { ...msg, id: genId(), timestamp: new Date() }
        set((s: AppState) => ({ messages: [...s.messages, full] }))
        return full
      },

      updateLastAssistantMessage: (response: ChatResponse) => {
        set((s: AppState) => {
          const msgs = [...s.messages]
          for (let i = msgs.length - 1; i >= 0; i--) {
            if (msgs[i].role === 'assistant') {
              msgs[i] = { ...msgs[i], content: response.message, response }
              break
            }
          }
          return { messages: msgs }
        })
      },

      setLoading: (loading: boolean) => set({ isLoading: loading }),
      setError: (error: string | null) => set({ error }),

      clearSession: () =>
        set({ sessionId: null, messages: [], error: null }),
    }),
    {
      name: 'bi-platform-store',
      partialize: (s: AppState & Actions) => ({
        sessionId: s.sessionId,
        messages: s.messages,
      }),
    }
  )
)