-- The transcript stops expiring.
--
-- Every line written before this migration carries a 90-day deadline, and the
-- retention sweep runs at every startup. Without this, the words the product
-- now promises to keep would still be deleted on schedule — the promise would
-- hold only for conversations that happened after the upgrade, which is the
-- worst version: silently true for new data and silently false for old.
--
-- NULL is the schema's own word for durable. Structured records already use it.
UPDATE session_message SET expires_at = NULL WHERE expires_at IS NOT NULL;
