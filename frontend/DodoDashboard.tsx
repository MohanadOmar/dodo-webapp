/**
 * Dodo V2 — Client Portal Dashboard
 *
 * Drop this into your Lovable project at src/pages/portal/dashboard.tsx
 * (or src/pages/Dashboard.tsx and add a route).
 *
 * Required env vars (Vite):
 *   VITE_DODO_API_URL     — e.g. https://dodo.railway.app
 *   VITE_CHAT_API_KEY     — same as CHAT_API_KEY on the backend
 *
 * Assumes the standard Lovable Supabase client at:
 *   src/integrations/supabase/client.ts  →  export { supabase }
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { supabase } from "@/integrations/supabase/client";

// ─── Config ──────────────────────────────────────────────────────────────────

const API = (import.meta.env.VITE_DODO_API_URL || "").replace(/\/$/, "");
const API_KEY = import.meta.env.VITE_CHAT_API_KEY || "";

const authHeaders = () => ({
  "Content-Type": "application/json",
  ...(API_KEY ? { Authorization: `Bearer ${API_KEY}` } : {}),
});

// ─── Brand tokens ─────────────────────────────────────────────────────────────

const C = {
  bg: "#0a0a0a",
  card: "#111111",
  border: "#1f1f1f",
  blue: "#4F46E5",
  purple: "#9333EA",
  text: "#ffffff",
  muted: "rgba(255,255,255,0.55)",
  success: "#22c55e",
  danger: "#ef4444",
};

// ─── Types ────────────────────────────────────────────────────────────────────

interface Profile {
  full_name: string;
  nickname: string;
  timezone: string;
  brief_about: string;
  messaging_channel: "sms" | "whatsapp";
  phone_number: string;
  whatsapp_number: string;
}

interface Integration {
  key: string;
  label: string;
  icon: string;
  connected: boolean;
}

interface KBDoc {
  source_name: string;
  created_at: string;
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

const TIMEZONES = [
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/Phoenix",
  "America/Anchorage",
  "Pacific/Honolulu",
  "Europe/London",
  "Europe/Paris",
  "Europe/Berlin",
  "Europe/Moscow",
  "Asia/Dubai",
  "Asia/Kolkata",
  "Asia/Bangkok",
  "Asia/Shanghai",
  "Asia/Tokyo",
  "Asia/Seoul",
  "Australia/Sydney",
  "Pacific/Auckland",
];

const INTEGRATION_DEFS = [
  { key: "gmail", label: "Gmail", icon: "✉️" },
  { key: "google_calendar", label: "Google Calendar", icon: "📅" },
  { key: "google_contacts", label: "Google Contacts", icon: "👤" },
  { key: "google_docs", label: "Google Docs", icon: "📄" },
  { key: "google_sheets", label: "Google Sheets", icon: "📊" },
  { key: "notion", label: "Notion", icon: "⬛" },
];

// ─── Toast ────────────────────────────────────────────────────────────────────

interface Toast {
  id: number;
  message: string;
  type: "success" | "error";
}

let _toastId = 0;

function useToast() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const show = useCallback((message: string, type: "success" | "error" = "success") => {
    const id = ++_toastId;
    setToasts((t) => [...t, { id, message, type }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3500);
  }, []);

  return { toasts, show };
}

function ToastStack({ toasts }: { toasts: Toast[] }) {
  return (
    <div style={{ position: "fixed", bottom: 24, right: 24, zIndex: 9999, display: "flex", flexDirection: "column", gap: 8 }}>
      {toasts.map((t) => (
        <div
          key={t.id}
          style={{
            background: t.type === "success" ? C.success : C.danger,
            color: "#fff",
            padding: "10px 18px",
            borderRadius: 8,
            fontFamily: "Inter, sans-serif",
            fontSize: 14,
            fontWeight: 500,
            boxShadow: "0 4px 20px rgba(0,0,0,0.4)",
            animation: "slideIn 0.2s ease",
          }}
        >
          {t.message}
        </div>
      ))}
    </div>
  );
}

// ─── Small components ─────────────────────────────────────────────────────────

function SectionHeading({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div style={{ marginBottom: 24 }}>
      <h2 style={{ fontSize: 20, fontWeight: 700, color: C.text, letterSpacing: "-0.02em", margin: 0 }}>{title}</h2>
      {subtitle && <p style={{ color: C.muted, fontSize: 14, marginTop: 6, marginBottom: 0 }}>{subtitle}</p>}
    </div>
  );
}

function Card({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div
      style={{
        background: C.card,
        border: `1px solid ${C.border}`,
        borderRadius: 12,
        padding: 28,
        ...style,
      }}
    >
      {children}
    </div>
  );
}

function Btn({
  children,
  onClick,
  loading,
  variant = "primary",
  small,
  style,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  loading?: boolean;
  variant?: "primary" | "ghost" | "danger";
  small?: boolean;
  style?: React.CSSProperties;
}) {
  const bg =
    variant === "primary"
      ? `linear-gradient(135deg, ${C.blue} 0%, ${C.purple} 100%)`
      : variant === "danger"
      ? C.danger
      : "transparent";
  const border = variant === "ghost" ? `1px solid ${C.border}` : "none";
  return (
    <button
      onClick={onClick}
      disabled={loading}
      style={{
        background: bg,
        border,
        color: C.text,
        borderRadius: 8,
        padding: small ? "7px 16px" : "10px 22px",
        fontSize: small ? 13 : 14,
        fontWeight: 600,
        cursor: loading ? "not-allowed" : "pointer",
        opacity: loading ? 0.6 : 1,
        fontFamily: "Inter, sans-serif",
        transition: "opacity 0.15s",
        ...style,
      }}
    >
      {loading ? "..." : children}
    </button>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <label style={{ color: C.muted, fontSize: 13, fontWeight: 500 }}>{label}</label>
      {children}
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  background: "#1a1a1a",
  border: `1px solid ${C.border}`,
  borderRadius: 8,
  padding: "10px 14px",
  color: C.text,
  fontSize: 14,
  fontFamily: "Inter, sans-serif",
  outline: "none",
  width: "100%",
  boxSizing: "border-box",
};

// ─── Section 1: Profile ───────────────────────────────────────────────────────

function ProfileSection({ userId, toast }: { userId: string; toast: (m: string, t?: "success" | "error") => void }) {
  const [form, setForm] = useState<Partial<Profile>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    supabase
      .from("client_profiles")
      .select("full_name, nickname, timezone, brief_about")
      .eq("user_id", userId)
      .single()
      .then(({ data }) => {
        if (data) setForm(data as Partial<Profile>);
        setLoading(false);
      });
  }, [userId]);

  const save = async () => {
    setSaving(true);
    const { error } = await supabase
      .from("client_profiles")
      .upsert({ user_id: userId, ...form }, { onConflict: "user_id" });
    setSaving(false);
    if (error) toast("Failed to save profile", "error");
    else toast("Profile saved");
  };

  if (loading) return <Card><p style={{ color: C.muted }}>Loading...</p></Card>;

  return (
    <Card>
      <SectionHeading title="Profile" />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
        <Field label="Full name">
          <input
            style={inputStyle}
            value={form.full_name || ""}
            onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            placeholder="Your full name"
          />
        </Field>
        <Field label="Nickname">
          <input
            style={inputStyle}
            value={form.nickname || ""}
            onChange={(e) => setForm({ ...form, nickname: e.target.value })}
            placeholder="What Dodo calls you"
          />
        </Field>
        <Field label="Timezone">
          <select
            style={{ ...inputStyle, appearance: "none" }}
            value={form.timezone || "America/Chicago"}
            onChange={(e) => setForm({ ...form, timezone: e.target.value })}
          >
            {TIMEZONES.map((tz) => (
              <option key={tz} value={tz} style={{ background: "#1a1a1a" }}>
                {tz}
              </option>
            ))}
          </select>
        </Field>
        <div />
        <Field label="About your business">
          <textarea
            style={{ ...inputStyle, minHeight: 80, resize: "vertical", gridColumn: "1 / -1" }}
            value={form.brief_about || ""}
            onChange={(e) => setForm({ ...form, brief_about: e.target.value })}
            placeholder="Briefly describe your business so Dodo can give better answers..."
          />
        </Field>
      </div>
      <div style={{ marginTop: 24 }}>
        <Btn onClick={save} loading={saving}>Save profile</Btn>
      </div>
    </Card>
  );
}

// ─── Section 2: Messaging Channel ────────────────────────────────────────────

function MessagingSection({ userId, toast }: { userId: string; toast: (m: string, t?: "success" | "error") => void }) {
  const [channel, setChannel] = useState<"sms" | "whatsapp">("sms");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [whatsappNumber, setWhatsappNumber] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    supabase
      .from("client_profiles")
      .select("messaging_channel, phone_number, whatsapp_number")
      .eq("user_id", userId)
      .single()
      .then(({ data }) => {
        if (data) {
          setChannel((data.messaging_channel as "sms" | "whatsapp") || "sms");
          setPhoneNumber(data.phone_number || "");
          setWhatsappNumber(data.whatsapp_number || "");
        }
        setLoading(false);
      });
  }, [userId]);

  const save = async () => {
    setSaving(true);
    const { error } = await supabase
      .from("client_profiles")
      .upsert(
        {
          user_id: userId,
          messaging_channel: channel,
          phone_number: channel === "sms" ? phoneNumber : undefined,
          whatsapp_number: channel === "whatsapp" ? whatsappNumber : undefined,
        },
        { onConflict: "user_id" }
      );
    setSaving(false);
    if (error) toast("Failed to save", "error");
    else toast("Messaging channel saved");
  };

  const channelCard = (type: "sms" | "whatsapp", icon: string, label: string, subtext: string) => {
    const active = channel === type;
    return (
      <div
        onClick={() => setChannel(type)}
        style={{
          flex: 1,
          background: active ? "rgba(79,70,229,0.1)" : "#1a1a1a",
          border: `2px solid ${active ? C.blue : C.border}`,
          borderRadius: 12,
          padding: 20,
          cursor: "pointer",
          transition: "all 0.15s",
          boxShadow: active ? `0 0 0 2px ${C.blue}33` : "none",
        }}
      >
        <div style={{ fontSize: 28, marginBottom: 8 }}>{icon}</div>
        <div style={{ fontWeight: 700, color: C.text, fontSize: 15 }}>{label}</div>
        <div style={{ color: C.muted, fontSize: 13, marginTop: 4 }}>{subtext}</div>
      </div>
    );
  };

  if (loading) return <Card><p style={{ color: C.muted }}>Loading...</p></Card>;

  return (
    <Card>
      <SectionHeading title="How Dodo reaches you" subtitle="Choose how Dodo sends you messages outside the web portal." />
      <div style={{ display: "flex", gap: 16, marginBottom: 24 }}>
        {channelCard("sms", "💬", "SMS", "Via text message (US numbers)")}
        {channelCard("whatsapp", "📱", "WhatsApp", "Works globally")}
      </div>
      {channel === "sms" && (
        <Field label="Your phone number">
          <input
            style={{ ...inputStyle, maxWidth: 320 }}
            value={phoneNumber}
            onChange={(e) => setPhoneNumber(e.target.value)}
            placeholder="+1 (555) 000-0000"
          />
        </Field>
      )}
      {channel === "whatsapp" && (
        <Field label="Your WhatsApp number">
          <input
            style={{ ...inputStyle, maxWidth: 320 }}
            value={whatsappNumber}
            onChange={(e) => setWhatsappNumber(e.target.value)}
            placeholder="+20 100 000 0000"
          />
        </Field>
      )}
      <div style={{ marginTop: 20 }}>
        <Btn onClick={save} loading={saving}>Save</Btn>
      </div>
    </Card>
  );
}

// ─── Section 3: Integrations ──────────────────────────────────────────────────

function IntegrationsSection({ userId, toast }: { userId: string; toast: (m: string, t?: "success" | "error") => void }) {
  const [integrations, setIntegrations] = useState<Integration[]>(
    INTEGRATION_DEFS.map((d) => ({ ...d, connected: false }))
  );
  const [busy, setBusy] = useState<string | null>(null);

  const loadConnections = useCallback(async () => {
    const { data } = await supabase
      .from("client_connections")
      .select("integration, status")
      .eq("user_id", userId);
    const connectedSet = new Set(
      (data || []).filter((r) => r.status === "connected").map((r) => r.integration)
    );
    setIntegrations(INTEGRATION_DEFS.map((d) => ({ ...d, connected: connectedSet.has(d.key) })));
  }, [userId]);

  useEffect(() => { loadConnections(); }, [loadConnections]);

  const notifyBackend = async (integration: string, action: "connected" | "disconnected") => {
    try {
      await fetch(`${API}/chat/connection-update`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ user_id: userId, integration, action }),
      });
    } catch {
      // non-critical
    }
  };

  const disconnect = async (key: string, label: string) => {
    setBusy(key);
    const { error } = await supabase
      .from("client_connections")
      .delete()
      .eq("user_id", userId)
      .eq("integration", key);
    if (error) {
      toast(`Failed to disconnect ${label}`, "error");
    } else {
      await notifyBackend(key, "disconnected");
      await loadConnections();
      toast(`${label} disconnected`);
    }
    setBusy(null);
  };

  const connect = (key: string, label: string) => {
    // OAuth connect — open the OAuth flow URL if configured, else show coming soon
    const oauthUrl = (import.meta.env as Record<string, string>)[`VITE_OAUTH_${key.toUpperCase()}_URL`];
    if (oauthUrl) {
      window.open(oauthUrl, "_blank");
    } else {
      toast(`${label} OAuth coming soon — ask your EG23 team to connect it.`, "error");
    }
  };

  return (
    <Card>
      <SectionHeading title="Connect your tools" subtitle="Dodo can only access a tool once you've connected it here." />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 14 }}>
        {integrations.map((intg) => (
          <div
            key={intg.key}
            style={{
              background: "#1a1a1a",
              border: `1px solid ${C.border}`,
              borderRadius: 10,
              padding: "16px 20px",
              display: "flex",
              alignItems: "center",
              gap: 14,
            }}
          >
            <span style={{ fontSize: 26 }}>{intg.icon}</span>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, color: C.text, fontSize: 14 }}>{intg.label}</div>
              <div
                style={{
                  fontSize: 12,
                  marginTop: 3,
                  color: intg.connected ? C.success : C.muted,
                  fontWeight: 500,
                }}
              >
                {intg.connected ? "● Connected" : "○ Not connected"}
              </div>
            </div>
            {intg.connected ? (
              <Btn
                variant="ghost"
                small
                loading={busy === intg.key}
                onClick={() => disconnect(intg.key, intg.label)}
              >
                Disconnect
              </Btn>
            ) : (
              <Btn
                variant="primary"
                small
                loading={busy === intg.key}
                onClick={() => connect(intg.key, intg.label)}
              >
                Connect
              </Btn>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
}

// ─── Section 4: Knowledge Base ────────────────────────────────────────────────

function KnowledgeSection({ userId, toast }: { userId: string; toast: (m: string, t?: "success" | "error") => void }) {
  const [docs, setDocs] = useState<KBDoc[]>([]);
  const [loadingDocs, setLoadingDocs] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadDocs = useCallback(async () => {
    setLoadingDocs(true);
    try {
      const res = await fetch(`${API}/knowledge/list?user_id=${encodeURIComponent(userId)}`, {
        headers: authHeaders(),
      });
      const data = await res.json();
      setDocs(data.documents || []);
    } catch {
      toast("Could not load documents", "error");
    }
    setLoadingDocs(false);
  }, [userId]);

  useEffect(() => { loadDocs(); }, [loadDocs]);

  const uploadFile = async (file: File) => {
    if (!file.name.match(/\.(pdf|txt)$/i)) {
      toast("Only .pdf and .txt files are supported", "error");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      toast("File must be under 10MB", "error");
      return;
    }
    setUploading(true);
    const fd = new FormData();
    fd.append("file", file);
    fd.append("user_id", userId);
    try {
      const res = await fetch(`${API}/knowledge/upload`, {
        method: "POST",
        headers: API_KEY ? { Authorization: `Bearer ${API_KEY}` } : {},
        body: fd,
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      toast(`Uploaded "${data.file}" (${data.chunks_uploaded} chunks)`);
      await loadDocs();
    } catch (e: unknown) {
      toast(`Upload failed: ${e instanceof Error ? e.message : String(e)}`, "error");
    }
    setUploading(false);
  };

  const deleteDoc = async (sourceName: string) => {
    setDeleting(sourceName);
    try {
      const res = await fetch(
        `${API}/knowledge/delete?user_id=${encodeURIComponent(userId)}&source_name=${encodeURIComponent(sourceName)}`,
        { method: "DELETE", headers: authHeaders() }
      );
      if (!res.ok) throw new Error(await res.text());
      toast(`"${sourceName}" deleted`);
      await loadDocs();
    } catch {
      toast("Delete failed", "error");
    }
    setDeleting(null);
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) uploadFile(file);
  };

  return (
    <Card>
      <SectionHeading
        title="Dodo's memory about your business"
        subtitle="Upload documents so Dodo can answer questions about your business accurately."
      />

      {/* Upload area */}
      <div
        onDrop={onDrop}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onClick={() => !uploading && fileInputRef.current?.click()}
        style={{
          border: `2px dashed ${dragOver ? C.blue : C.border}`,
          borderRadius: 10,
          padding: "36px 20px",
          textAlign: "center",
          cursor: uploading ? "not-allowed" : "pointer",
          transition: "border-color 0.15s",
          background: dragOver ? "rgba(79,70,229,0.05)" : "transparent",
          marginBottom: 24,
        }}
      >
        <div style={{ fontSize: 32, marginBottom: 8 }}>📎</div>
        <p style={{ color: C.text, fontWeight: 600, marginBottom: 4 }}>
          {uploading ? "Uploading..." : "Drop a file or click to upload"}
        </p>
        <p style={{ color: C.muted, fontSize: 13 }}>Accepts .pdf and .txt — max 10MB</p>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.txt"
          style={{ display: "none" }}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadFile(f); e.target.value = ""; }}
        />
      </div>

      {/* Document list */}
      {loadingDocs ? (
        <p style={{ color: C.muted }}>Loading documents...</p>
      ) : docs.length === 0 ? (
        <p style={{ color: C.muted, fontSize: 14 }}>
          No documents yet. Upload your SOPs, FAQs, or any business docs.
        </p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {docs.map((doc) => (
            <div
              key={doc.source_name}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 14,
                background: "#1a1a1a",
                borderRadius: 8,
                padding: "12px 16px",
              }}
            >
              <span style={{ fontSize: 18 }}>📄</span>
              <div style={{ flex: 1 }}>
                <div style={{ color: C.text, fontSize: 14, fontWeight: 500 }}>{doc.source_name}</div>
                <div style={{ color: C.muted, fontSize: 12 }}>
                  {new Date(doc.created_at).toLocaleDateString()}
                </div>
              </div>
              <button
                onClick={() => deleteDoc(doc.source_name)}
                disabled={deleting === doc.source_name}
                style={{
                  background: "none",
                  border: "none",
                  color: C.danger,
                  cursor: "pointer",
                  fontSize: 18,
                  padding: "4px 8px",
                  opacity: deleting === doc.source_name ? 0.4 : 1,
                }}
                title="Delete"
              >
                🗑️
              </button>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

// ─── Section 5: Chat with Dodo ────────────────────────────────────────────────

function ChatSection({ userId }: { userId: string }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async () => {
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: text }]);
    setSending(true);
    try {
      const res = await fetch(`${API}/chat/message`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ message: text, user_id: userId, session_id: sessionId }),
      });
      const data = await res.json();
      if (data.session_id && !sessionId) setSessionId(data.session_id);
      setMessages((m) => [...m, { role: "assistant", content: data.reply || "..." }]);
    } catch {
      setMessages((m) => [...m, { role: "assistant", content: "Something went wrong. Please try again." }]);
    }
    setSending(false);
  };

  return (
    <Card style={{ display: "flex", flexDirection: "column", padding: 0, overflow: "hidden" }}>
      <div style={{ padding: "24px 28px 16px", borderBottom: `1px solid ${C.border}` }}>
        <SectionHeading title="Chat with Dodo" subtitle="Your AI assistant is ready." />
      </div>

      {/* Message list */}
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "20px 28px",
          minHeight: 300,
          maxHeight: 480,
          display: "flex",
          flexDirection: "column",
          gap: 12,
        }}
      >
        {messages.length === 0 && (
          <p style={{ color: C.muted, fontSize: 14, textAlign: "center", marginTop: 40 }}>
            Say hello to Dodo 👋
          </p>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            style={{
              display: "flex",
              justifyContent: m.role === "user" ? "flex-end" : "flex-start",
            }}
          >
            <div
              style={{
                background:
                  m.role === "user"
                    ? `linear-gradient(135deg, ${C.blue} 0%, ${C.purple} 100%)`
                    : "#1e1e1e",
                color: C.text,
                borderRadius: m.role === "user" ? "16px 16px 4px 16px" : "16px 16px 16px 4px",
                padding: "10px 16px",
                maxWidth: "75%",
                fontSize: 14,
                lineHeight: 1.5,
                whiteSpace: "pre-wrap",
              }}
            >
              {m.content}
            </div>
          </div>
        ))}
        {sending && (
          <div style={{ display: "flex", justifyContent: "flex-start" }}>
            <div style={{ background: "#1e1e1e", borderRadius: "16px 16px 16px 4px", padding: "10px 16px", color: C.muted, fontSize: 14 }}>
              Thinking...
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div
        style={{
          padding: "16px 28px 20px",
          borderTop: `1px solid ${C.border}`,
          display: "flex",
          gap: 10,
        }}
      >
        <input
          style={{ ...inputStyle, flex: 1 }}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && send()}
          placeholder="Message Dodo..."
          disabled={sending}
        />
        <Btn onClick={send} loading={sending} style={{ whiteSpace: "nowrap" }}>
          Send
        </Btn>
      </div>
    </Card>
  );
}

// ─── Main Dashboard ───────────────────────────────────────────────────────────

export default function DodoDashboard() {
  const [userId, setUserId] = useState<string | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const { toasts, show: toast } = useToast();

  useEffect(() => {
    supabase.auth.getUser().then(({ data }) => {
      setUserId(data?.user?.id || null);
      setAuthLoading(false);
    });
    const { data: sub } = supabase.auth.onAuthStateChange((_event, session) => {
      setUserId(session?.user?.id || null);
    });
    return () => sub.subscription.unsubscribe();
  }, []);

  if (authLoading) {
    return (
      <div style={{ background: C.bg, minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "Inter, sans-serif" }}>
        <p style={{ color: C.muted }}>Loading...</p>
      </div>
    );
  }

  if (!userId) {
    return (
      <div style={{ background: C.bg, minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "Inter, sans-serif" }}>
        <p style={{ color: C.muted }}>Please sign in to access your dashboard.</p>
      </div>
    );
  }

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        * { box-sizing: border-box; }
        body { background: ${C.bg}; }
        input, textarea, select { color-scheme: dark; }
        input::placeholder, textarea::placeholder { color: rgba(255,255,255,0.3); }
        @keyframes slideIn { from { transform: translateX(40px); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: ${C.border}; border-radius: 3px; }
      `}</style>

      <div
        style={{
          background: C.bg,
          minHeight: "100vh",
          fontFamily: "Inter, sans-serif",
          color: C.text,
        }}
      >
        {/* Header */}
        <div
          style={{
            borderBottom: `1px solid ${C.border}`,
            padding: "18px 40px",
            display: "flex",
            alignItems: "center",
            gap: 12,
            background: "#0d0d0d",
          }}
        >
          <span style={{ fontSize: 28 }}>🦤</span>
          <span style={{ fontSize: 18, fontWeight: 700, letterSpacing: "-0.02em" }}>Dodo</span>
          <span style={{ color: C.muted, fontSize: 13, marginLeft: 4 }}>by EG23</span>
        </div>

        {/* Content */}
        <div style={{ maxWidth: 860, margin: "0 auto", padding: "48px 24px", display: "flex", flexDirection: "column", gap: 36 }}>
          <ProfileSection userId={userId} toast={toast} />
          <MessagingSection userId={userId} toast={toast} />
          <IntegrationsSection userId={userId} toast={toast} />
          <KnowledgeSection userId={userId} toast={toast} />
          <ChatSection userId={userId} />
        </div>
      </div>

      <ToastStack toasts={toasts} />
    </>
  );
}
