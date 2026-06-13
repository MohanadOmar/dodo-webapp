-- Dodo V2 migration: add WhatsApp support columns to client_profiles
-- Run this in the Supabase SQL editor

ALTER TABLE client_profiles
  ADD COLUMN IF NOT EXISTS messaging_channel text DEFAULT 'sms',
  ADD COLUMN IF NOT EXISTS whatsapp_number text;

-- Optional: add a check constraint so only valid values are stored
ALTER TABLE client_profiles
  ADD CONSTRAINT messaging_channel_values
  CHECK (messaging_channel IN ('sms', 'whatsapp'));

COMMENT ON COLUMN client_profiles.messaging_channel IS 'Preferred outbound channel: sms or whatsapp';
COMMENT ON COLUMN client_profiles.whatsapp_number IS 'WhatsApp phone number in E.164 format (e.g. +201001234567)';
