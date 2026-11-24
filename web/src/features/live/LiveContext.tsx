import { createContext, useContext, type ReactNode } from 'react'
import { useLiveEvents } from './useLiveEvents'

type Live = ReturnType<typeof useLiveEvents>
const Ctx = createContext<Live>({ ticker: [], conn: 'connecting', pulses: [] })

export function LiveProvider({ children }: { children: ReactNode }) {
  return <Ctx.Provider value={useLiveEvents()}>{children}</Ctx.Provider>
}
export const useLive = () => useContext(Ctx)
