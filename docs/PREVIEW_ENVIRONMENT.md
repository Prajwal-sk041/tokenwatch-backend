# Preview environment

Preview deployments must use an isolated Supabase project and preview-only secrets. Production database credentials are forbidden. If preview variables are absent, settings validation intentionally stops startup with a clear configuration error instead of serving a partially functional API. Preview email uses the safe preview mode; Stripe stays in test mode.
