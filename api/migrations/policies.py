"""Row-level security, grants and privileged functions for the v1 schema.

Kept apart from the table DDL so the security model reads as one document.
The app connects as `canopy_app`, which owns nothing, so these policies bind it.
"""

APP_ROLE = "canopy_app"

WORKSPACE_TABLES = (
    "invitations",
    "xero_connections",
    "entities",
    "entity_accounts",
    "sync_runs",
    "group_accounts",
    "account_mappings",
)

# Tables deliberately without RLS: looked up before any user/workspace context
# exists, and holding only hashes, ids, counters or short-lived OAuth state.
NO_RLS_TABLES = ("sessions", "oauth_states", "xero_quota", "alembic_version")

UPGRADE = f"""
-- Context helpers: NULL when unset, so policies fail closed.
CREATE FUNCTION canopy_current_workspace() RETURNS uuid
  LANGUAGE sql STABLE AS $$ SELECT nullif(current_setting('app.workspace_id', true), '')::uuid $$;
CREATE FUNCTION canopy_current_user() RETURNS uuid
  LANGUAGE sql STABLE AS $$ SELECT nullif(current_setting('app.user_id', true), '')::uuid $$;

GRANT USAGE ON SCHEMA public TO {APP_ROLE};

-- Workspace-owned tables: one policy, both directions.
{"".join(f'''
ALTER TABLE {t} ENABLE ROW LEVEL SECURITY;
CREATE POLICY workspace_isolation ON {t}
  USING (workspace_id = canopy_current_workspace())
  WITH CHECK (workspace_id = canopy_current_workspace());
GRANT SELECT, INSERT, UPDATE, DELETE ON {t} TO {APP_ROLE};
''' for t in WORKSPACE_TABLES)}

-- workspaces: members see it; the creator inserts it with its id bound as context.
ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY;
CREATE POLICY workspace_read ON workspaces FOR SELECT USING (
  id = canopy_current_workspace()
  OR EXISTS (SELECT 1 FROM memberships m WHERE m.workspace_id = workspaces.id AND m.user_id = canopy_current_user())
);
CREATE POLICY workspace_create ON workspaces FOR INSERT
  WITH CHECK (id = canopy_current_workspace() AND created_by = canopy_current_user());
CREATE POLICY workspace_update ON workspaces FOR UPDATE
  USING (id = canopy_current_workspace()) WITH CHECK (id = canopy_current_workspace());
GRANT SELECT, INSERT, UPDATE ON workspaces TO {APP_ROLE};

-- memberships: visible in the workspace, and to the member (to list their workspaces).
-- Writes only inside the current workspace.
ALTER TABLE memberships ENABLE ROW LEVEL SECURITY;
CREATE POLICY membership_read ON memberships FOR SELECT
  USING (workspace_id = canopy_current_workspace() OR user_id = canopy_current_user());
CREATE POLICY membership_write ON memberships FOR INSERT
  WITH CHECK (workspace_id = canopy_current_workspace());
CREATE POLICY membership_update ON memberships FOR UPDATE
  USING (workspace_id = canopy_current_workspace()) WITH CHECK (workspace_id = canopy_current_workspace());
CREATE POLICY membership_delete ON memberships FOR DELETE
  USING (workspace_id = canopy_current_workspace());
GRANT SELECT, INSERT, UPDATE, DELETE ON memberships TO {APP_ROLE};

-- users: yourself, plus people in your current workspace. Created only via
-- canopy_upsert_user (below); you may update only your own row.
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE POLICY user_read ON users FOR SELECT USING (
  id = canopy_current_user()
  OR EXISTS (SELECT 1 FROM memberships m WHERE m.user_id = users.id AND m.workspace_id = canopy_current_workspace())
);
CREATE POLICY user_update_self ON users FOR UPDATE
  USING (id = canopy_current_user()) WITH CHECK (id = canopy_current_user());
GRANT SELECT, UPDATE ON users TO {APP_ROLE};

-- audit_events: append-only (no UPDATE/DELETE grant).
ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY audit_read ON audit_events FOR SELECT USING (
  workspace_id = canopy_current_workspace()
  OR (workspace_id IS NULL AND actor_user_id = canopy_current_user())
);
CREATE POLICY audit_insert ON audit_events FOR INSERT WITH CHECK (
  workspace_id = canopy_current_workspace()
  OR (workspace_id IS NULL AND actor_user_id = canopy_current_user())
);
GRANT SELECT, INSERT ON audit_events TO {APP_ROLE};
GRANT USAGE ON SEQUENCE audit_events_id_seq TO {APP_ROLE};

-- No-RLS tables (see NO_RLS_TABLES).
GRANT SELECT, INSERT, UPDATE, DELETE ON sessions, oauth_states, xero_quota TO {APP_ROLE};

-- Login: create/refresh a user before any context exists.
CREATE FUNCTION canopy_upsert_user(p_xero_user_id text, p_email text, p_name text) RETURNS uuid
  LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
    INSERT INTO users (id, xero_user_id, email, name, created_at, last_login_at)
    VALUES (gen_random_uuid(), p_xero_user_id, p_email, coalesce(p_name, ''), now(), now())
    ON CONFLICT (xero_user_id) DO UPDATE
      SET email = excluded.email, name = excluded.name, last_login_at = now()
    RETURNING id
$$;

-- Accept an invitation for the CURRENT user (from app.user_id, never a
-- parameter), only if the invited email matches theirs.
CREATE FUNCTION canopy_accept_invitation(p_token_hash text)
  RETURNS TABLE (workspace_id uuid, role role)
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
  v_user uuid := canopy_current_user();
  v_inv invitations%ROWTYPE;
BEGIN
  IF v_user IS NULL THEN RETURN; END IF;
  SELECT i.* INTO v_inv FROM invitations i
    JOIN users u ON u.id = v_user AND lower(u.email) = lower(i.email)
   WHERE i.token_hash = p_token_hash AND i.accepted_at IS NULL AND i.expires_at > now()
   FOR UPDATE OF i;
  IF NOT FOUND THEN RETURN; END IF;
  INSERT INTO memberships (id, workspace_id, user_id, role, created_at)
    VALUES (gen_random_uuid(), v_inv.workspace_id, v_user, v_inv.role, now())
    -- By constraint name: the function's OUT columns (workspace_id, role) would
    -- otherwise be ambiguous with the table's columns here.
    ON CONFLICT ON CONSTRAINT uq_memberships_workspace_id_user_id DO NOTHING;
  UPDATE invitations SET accepted_at = now(), accepted_by = v_user WHERE id = v_inv.id;
  RETURN QUERY SELECT v_inv.workspace_id, v_inv.role;
END $$;

-- Scheduler: list active entities across workspaces (ids only) for the nightly sync.
CREATE FUNCTION canopy_active_entities()
  RETURNS TABLE (workspace_id uuid, entity_id uuid, tenant_id text)
  LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
    SELECT e.workspace_id, e.id, e.tenant_id FROM entities e WHERE e.status = 'active'
$$;

REVOKE ALL ON FUNCTION canopy_upsert_user(text, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION canopy_accept_invitation(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION canopy_active_entities() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION canopy_upsert_user(text, text, text) TO {APP_ROLE};
GRANT EXECUTE ON FUNCTION canopy_accept_invitation(text) TO {APP_ROLE};
GRANT EXECUTE ON FUNCTION canopy_active_entities() TO {APP_ROLE};
"""

DOWNGRADE = """
DROP FUNCTION IF EXISTS canopy_active_entities();
DROP FUNCTION IF EXISTS canopy_accept_invitation(text);
DROP FUNCTION IF EXISTS canopy_upsert_user(text, text, text);
DROP FUNCTION IF EXISTS canopy_current_user();
DROP FUNCTION IF EXISTS canopy_current_workspace();
"""


def procrastinate_grants() -> str:
    """Grants on the job queue's OWN objects only (names start with procrastinate_).
    Never grant schema-wide: that would silently re-open UPDATE/DELETE on
    audit_events and INSERT on users."""
    return f"""
DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE 'procrastinate%' LOOP
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON public.%I TO {APP_ROLE}', r.tablename);
  END LOOP;
  FOR r IN SELECT sequencename FROM pg_sequences WHERE schemaname = 'public' AND sequencename LIKE 'procrastinate%' LOOP
    EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE public.%I TO {APP_ROLE}', r.sequencename);
  END LOOP;
  FOR r IN SELECT p.oid::regprocedure AS fn FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = 'public' AND p.proname LIKE 'procrastinate%' LOOP
    EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO {APP_ROLE}', r.fn);
  END LOOP;
END $$;
"""
