-- Feature-based plan differentiation for the financial intelligence layer.
-- Payment credentials remain optional; these entitlements are activated by the
-- existing signed billing webhook when billing is configured later.
update public.plans
set entitlements = entitlements || case code
  when 'free' then '{"spend_forecast":false,"savings_ledger":false,"optimization_recommendations":false}'::jsonb
  when 'starter' then '{"spend_forecast":true,"savings_ledger":true,"optimization_recommendations":false}'::jsonb
  when 'pro' then '{"spend_forecast":true,"savings_ledger":true,"optimization_recommendations":true}'::jsonb
  when 'team' then '{"spend_forecast":true,"savings_ledger":true,"optimization_recommendations":true}'::jsonb
  when 'enterprise' then '{"spend_forecast":true,"savings_ledger":true,"optimization_recommendations":true}'::jsonb
  else '{}'::jsonb
end,
updated_at = now()
where code in ('free','starter','pro','team','enterprise');
