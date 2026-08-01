# Organization Model

Every TokenWatch resource belongs to exactly one organization.

Roles:

- `owner`: full tenant control, including ownership and administrative operations.
- `admin`: membership, keys, budgets, alerts, subscriptions, and audit access.
- `member`: normal operational access and provider-key management.
- `viewer`: read-only dashboards and history.

Registration creates a default organization and owner membership. Invitations store a hashed, expiring, single-use token and the intended email. Acceptance requires the signed-in identity to match that email. Requests resolve a tenant from the access token and verify active membership in the database. Service-role database access never replaces this application-level authorization check.

RLS provides defense in depth for direct Supabase authenticated access. Policies call the private membership helper and use cached `(select auth.uid())` predicates. SDK keys carry one organization identifier and cannot switch tenants.
