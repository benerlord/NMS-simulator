import { camelizeKeys } from '@/api/case'

export type WsTopic =
  | 'topology.saved'
  | 'topology.conflict'
  | 'log.request'
  | 'api.registered'

export interface WsEvent<T = unknown> {
  topic: WsTopic | string
  payload: T
  ts?: string
}

type Handler = (event: WsEvent) => void

interface Options {
  url?: string
  heartbeatMs?: number
  maxBackoffMs?: number
}

const DEFAULT_URL = () => {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${location.host}/admin/ws`
}

export class WsClient {
  private url: string
  private heartbeatMs: number
  private maxBackoffMs: number
  private ws: WebSocket | null = null
  private handlers = new Map<string, Set<Handler>>()
  private topics = new Set<string>()
  private retries = 0
  private heartbeatTimer: number | null = null
  private reconnectTimer: number | null = null
  private manualClose = false

  constructor(opts: Options = {}) {
    this.url = opts.url ?? DEFAULT_URL()
    this.heartbeatMs = opts.heartbeatMs ?? 30_000
    this.maxBackoffMs = opts.maxBackoffMs ?? 30_000
  }

  connect(): void {
    this.manualClose = false
    this.open()
  }

  close(): void {
    this.manualClose = true
    this.stopHeartbeat()
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    this.ws?.close()
    this.ws = null
  }

  on(topic: string, handler: Handler): () => void {
    let bucket = this.handlers.get(topic)
    if (!bucket) {
      bucket = new Set()
      this.handlers.set(topic, bucket)
    }
    bucket.add(handler)
    this.subscribe(topic)
    return () => this.off(topic, handler)
  }

  off(topic: string, handler: Handler): void {
    const bucket = this.handlers.get(topic)
    if (!bucket) return
    bucket.delete(handler)
    if (bucket.size === 0) {
      this.handlers.delete(topic)
      this.unsubscribe(topic)
    }
  }

  private subscribe(topic: string): void {
    if (this.topics.has(topic)) return
    this.topics.add(topic)
    this.send({ op: 'subscribe', topics: [topic] })
  }

  private unsubscribe(topic: string): void {
    if (!this.topics.delete(topic)) return
    this.send({ op: 'unsubscribe', topics: [topic] })
  }

  private send(msg: unknown): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg))
    }
  }

  private open(): void {
    const ws = new WebSocket(this.url)
    this.ws = ws

    ws.addEventListener('open', () => {
      this.retries = 0
      if (this.topics.size > 0) {
        this.send({ op: 'subscribe', topics: Array.from(this.topics) })
      }
      this.startHeartbeat()
    })

    ws.addEventListener('message', (ev) => {
      this.handleMessage(ev.data)
    })

    ws.addEventListener('close', () => {
      this.stopHeartbeat()
      if (!this.manualClose) this.scheduleReconnect()
    })

    ws.addEventListener('error', () => ws.close())
  }

  private handleMessage(raw: unknown): void {
    if (typeof raw !== 'string') return
    let msg: Record<string, unknown>
    try {
      msg = camelizeKeys(JSON.parse(raw))
    } catch {
      return
    }
    if (msg.op === 'pong') return
    const topic = typeof msg.topic === 'string' ? msg.topic : null
    if (!topic) return
    const bucket = this.handlers.get(topic)
    if (!bucket) return
    const event: WsEvent = {
      topic,
      payload: msg.payload as unknown,
      ts: typeof msg.ts === 'string' ? msg.ts : undefined,
    }
    bucket.forEach((fn) => fn(event))
  }

  private startHeartbeat(): void {
    this.stopHeartbeat()
    this.heartbeatTimer = window.setInterval(() => {
      this.send({ op: 'ping' })
    }, this.heartbeatMs)
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer !== null) {
      clearInterval(this.heartbeatTimer)
      this.heartbeatTimer = null
    }
  }

  private scheduleReconnect(): void {
    this.retries += 1
    const delay = Math.min(1000 * 2 ** this.retries, this.maxBackoffMs)
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null
      this.open()
    }, delay)
  }
}

let singleton: WsClient | null = null

export function getWsClient(): WsClient {
  if (!singleton) {
    singleton = new WsClient()
    singleton.connect()
  }
  return singleton
}
