/**
 * Real-time layer for the console.
 *
 * Opens one Server-Sent Events connection to /api/stream (same-origin, cookie-auth) for
 * the whole app and fans the traffic out to three things:
 *   - the notification bell (staff alerts: handover, booking, review, incidents),
 *   - the dashboard's live activity feed (inbound/outbound WhatsApp messages),
 *   - React Query, which we invalidate (debounced) so KPIs refresh themselves live.
 *
 * The connection is only held while authenticated; EventSource reconnects on its own, and
 * we surface that as a `connected` flag the AppBar renders as a live/offline pulse.
 */
import {
  createContext, useContext, useCallback, useEffect, useRef, useState, ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useSnackbar } from "notistack";
import { useAuth } from "./auth";
import { apiGet, apiPost } from "./api";

export type Level = "info" | "success" | "warning" | "error";

export interface Note {
  id: number;
  level: Level;
  title: string;
  body?: string;
  category?: string;
  tenant_id?: number | null;
  link?: string | null;
  wa_user?: string | null;
  ts: string;
}

export interface Activity {
  key: string;
  wa_user: string;
  direction: "in" | "out";
  text: string;
  intent?: string;
  needs_human?: boolean;
  ts: number;
}

interface Live {
  connected: boolean;
  notes: Note[];
  unread: number;
  activity: Activity[];
  typing: Set<string>;
  markAllRead: () => void;
  clear: () => void;
}

const LiveCtx = createContext<Live>(null as any);
export const useLive = () => useContext(LiveCtx);

const MAX_NOTES = 60;
const MAX_ACTIVITY = 40;
const variantFor: Record<Level, "info" | "success" | "warning" | "error"> = {
  info: "info", success: "success", warning: "warning", error: "error",
};

export function LiveProvider({ children }: { children: ReactNode }) {
  const { me } = useAuth();
  const qc = useQueryClient();
  const { enqueueSnackbar } = useSnackbar();

  const [connected, setConnected] = useState(false);
  const [notes, setNotes] = useState<Note[]>([]);
  const [unread, setUnread] = useState(0);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [typing, setTyping] = useState<Set<string>>(new Set());

  // Debounce query invalidation so a burst of messages refreshes the dashboard once.
  const flushTimer = useRef<number | null>(null);
  const scheduleRefresh = useCallback(() => {
    if (flushTimer.current != null) return;
    flushTimer.current = window.setTimeout(() => {
      flushTimer.current = null;
      ["dashboard", "overview", "trends", "conversations", "patient"].forEach((k) =>
        qc.invalidateQueries({ queryKey: [k] }));
    }, 1200);
  }, [qc]);

  // Persist "seen" so the unread badge stays cleared across refreshes and other sessions.
  const markAllRead = useCallback(() => {
    setUnread(0);
    apiPost("/notifications/seen").catch(() => {});
  }, []);
  const clear = useCallback(() => { setNotes([]); markAllRead(); }, [markAllRead]);

  useEffect(() => {
    if (!me) { setConnected(false); return; }
    let cancelled = false;

    // Seed the bell with durable history + the durable unread count (survives refresh/restart).
    apiGet<{ notifications: Note[]; unread: number }>("/notifications")
      .then((d) => { if (!cancelled) { setNotes(d.notifications || []); setUnread(d.unread || 0); } })
      .catch(() => {});

    const es = new EventSource("/api/stream");
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false); // EventSource retries automatically

    es.onmessage = (e) => {
      let ev: any;
      try { ev = JSON.parse(e.data); } catch { return; }

      if (ev.type === "notification") {
        const note = ev as Note;
        setNotes((prev) => [note, ...prev].slice(0, MAX_NOTES));
        setUnread((u) => u + 1);
        enqueueSnackbar(note.title, { variant: variantFor[note.level] ?? "info" });
        scheduleRefresh();
      } else if (ev.type === "message") {
        const item: Activity = {
          key: `${ev.seq}-${ev.wa_user}`,
          wa_user: ev.wa_user, direction: ev.direction, text: ev.text,
          intent: ev.intent, needs_human: ev.needs_human, ts: Date.now(),
        };
        setActivity((prev) => [item, ...prev].slice(0, MAX_ACTIVITY));
        setTyping((prev) => {
          if (!prev.has(ev.wa_user)) return prev;
          const next = new Set(prev); next.delete(ev.wa_user); return next;
        });
        scheduleRefresh();
      } else if (ev.type === "typing") {
        setTyping((prev) => new Set(prev).add(ev.wa_user));
      } else if (ev.type === "stoptyping") {
        setTyping((prev) => {
          if (!prev.has(ev.wa_user)) return prev;
          const next = new Set(prev); next.delete(ev.wa_user); return next;
        });
      }
    };

    return () => {
      cancelled = true;
      es.close();
      setConnected(false);
      if (flushTimer.current != null) { clearTimeout(flushTimer.current); flushTimer.current = null; }
    };
  }, [me, enqueueSnackbar, scheduleRefresh]);

  return (
    <LiveCtx.Provider value={{ connected, notes, unread, activity, typing, markAllRead, clear }}>
      {children}
    </LiveCtx.Provider>
  );
}
