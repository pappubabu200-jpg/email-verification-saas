<!-- TREE_START -->

```text
email-verification-saas/
├── .github/
│   └── workflows/
│       ├── codeql.yml
│       └── update-tree.yml
├── Backend/
│   ├── .env.prod
│   ├── .environment.dev
│   ├── docker-compose.yml
│   ├── requirements.txt
│   ├── billing/
│   │   ├── __init__.py
│   │   ├── plans.py
│   │   ├── razorpay_handlers.py
│   │   ├── stripe_handlers.py
│   │   └── upi_handlers.py
│   ├── scripts/
│   │   └── simulate_bulk_job.py
│   ├── tests/ (17 test files)
│   └── app/
│       ├── __init__.py
│       ├── celery_app.py
│       ├── config.py
│       ├── db.py
│       ├── main.py
│       ├── utils/
│       │   ├── __init__.py
│       │   ├── hashing.py
│       │   ├── helpers.py
│       │   └── security.py
│       ├── tasks/
│       │   ├── bulk_tasks.py
│       │   ├── dlq_retry.py
│       │   ├── dlq_retry_task.py
│       │   ├── process_bulk.py
│       │   ├── scheduled.py
│       │   └── webhook_tasks.py
│       ├── workers/
│       │   ├── __init__.py
│       │   ├── billing_tasks.py
│       │   ├── bulk_tasks.py
│       │   ├── decision_maker_tasks.py
│       │   ├── extractor_task_async.py
│       │   ├── extractor_tasks.py
│       │   ├── job_watcher.py
│       │   ├── scheduler.py
│       │   └── tasks.py
│       ├── models/                         ← 24 SQLAlchemy Models
│       │   ├── __init__.py
│       │   ├── api_key.py
│       │   ├── api_usage_summary.py
│       │   ├── audit_log.py
│       │   ├── base.py
│       │   ├── bulk_job.py
│       │   ├── credit_reservation.py
│       │   ├── credit_transaction.py
│       │   ├── decision_maker.py
│       │   ├── domain_cache.py
│       │   ├── extractor_job.py
│       │   ├── failed_job.py
│       │   ├── plan.py
│       │   ├── subscription.py
│       │   ├── suppression.py
│       │   ├── team.py
│       │   ├── team_balance.py
│       │   ├── team_credit_transaction.py
│       │   ├── team_member.py
│       │   ├── usage_log.py
│       │   ├── user.py
│       │   ├── verification_result.py
│       │   ├── webhook_dlq.py
│       │   ├── webhook_endpoint.py
│       │   └── webhook_event.py
│       ├── schemas/                        ← 23 Pydantic Schemas
│       │   ├── api_key.py
│       │   ├── api_usage_summary.py
│       │   ├── audit_log.py
│       │   ├── base.py
│       │   ├── bulk_job.py
│       │   ├── credit_reservation.py
│       │   ├── credit_transaction.py
│       │   ├── decision_maker.py
│       │   ├── domain_cache.py
│       │   ├── extractor_job.py
│       │   ├── failed_job.py
│       │   ├── plan.py
│       │   ├── subscription.py
│       │   ├── suppression.py
│       │   ├── team.py
│       │   ├── team_balance.py
│       │   ├── team_credit_transaction.py
│       │   ├── team_member.py
│       │   ├── usage_log.py
│       │   ├── user.py
│       │   ├── verification_result.py
│       │   ├── webhook_endpoint.py
│       │   └── webhook_event.py
│       ├── services/                       ← 50+ Core Services
│       │   ├── __init__.py
│       │   ├── acl_matrix.py
│       │   ├── analytics.py
│       │   ├── api_key_service.py
│       │   ├── apollo_client.py
│       │   ├── auth_service.py
│       │   ├── auto_topup.py
│       │   ├── billing_service.py
│       │   ├── bounce_classifier.py
│       │   ├── bulk_processor.py
│       │   ├── cache.py
│       │   ├── credits_service.py
│       │   ├── csv_parser.py
│       │   ├── decision_cache.py
│       │   ├── decision_maker_service.py
│       │   ├── decision_quota.py
│       │   ├── deliverability_monitor.py
│       │   ├── disposable_detector.py
│       │   ├── domain_backoff.py
│       │   ├── domain_throttle.py
│       │   ├── email_pattern_engine.py
│       │   ├── extractor_engine.py
│       │   ├── grok_client.py
│       │   ├── ip_intelligence.py
│       │   ├── minio_client.py
│       │   ├── minio_signed_url.py
│       │   ├── monitoring_service.py
│       │   ├── mx_lookup.py
│       │   ├── pattern_verifier.py
│       │   ├── pdl_client.py
│       │   ├── plan_service.py
│       │   ├── pricing_service.py
│       │   ├── processing_lock.py
│       │   ├── redis_rate_limiter.py
│       │   ├── reservation_finalizer.py
│       │   ├── smtp_probe.py
│       │   ├── spam_checker.py
│       │   ├── storage_s3.py
│       │   ├── stripe_handlers.py
│       │   ├── subscription_service.py
│       │   ├── team_billing_service.py
│       │   ├── team_check.py
│       │   ├── team_context.py
│       │   ├── team_service.py
│       │   ├── usage_service.py
│       │   ├── verification_engine.py
│       │   ├── verification_score.py
│       │   ├── webhook_dispatcher.py
│       │   ├── webhook_sender.py
│       │   └── webhook_service.py
│       ├── repositories/                   ← 21 Repositories
│       │   ├── api_key_repository.py
│       │   ├── audit_log_repository.py
│       │   ├── base.py
│       │   ├── bulk_job_repository.py
│       │   ├── credit_reservation_repository.py
│       │   ├── credit_transaction_repository.py
│       │   ├── decision_maker_repository.py
│       │   ├── domain_cache_repository.py
│       │   ├── extractor_job_repository.py
│       │   ├── failed_job_repository.py
│       │   ├── plan_repository.py
│       │   ├── subscription_repository.py
│       │   ├── suppression_repository.py
│       │   ├── team_member_repository.py
│       │   ├── team_repository.py
│       │   ├── usage_log_repository.py
│       │   ├── user_repository.py
│       │   ├── verification_result_repository.py
│       │   ├── webhook_dlq_repository.py
│       │   ├── webhook_endpoint_repository.py
│       │   └── webhook_event_repository.py
│       ├── routers/                        ← 13 Modern Routers
│       │   ├── admin.py
│       │   ├── api_keys.py
│       │   ├── auth.py
│       │   ├── billing.py
│       │   ├── bulk_jobs.py
│       │   ├── decision_maker.py
│       │   ├── suppression.py
│       │   ├── team.py
│       │   ├── usage_logs.py
│       │   ├── users.py
│       │   ├── verification.py
│       │   ├── webhook_endpoint.py
│       │   └── webhook_event.py
│       ├── middleware/
│       │   ├── __init__.py
│       │   ├── api_key_guard.py
│       │   ├── audit_middleware.py
│       │   ├── cors.py
│       │   ├── rate_limiter.py
│       │   ├── request_logger.py
│       │   ├── team_acl.py
│       │   └── team_context.py
│       ├── admin_extra/
│       │   ├── __init__.py
│       │   ├── charts.py
│       │   ├── exports.py
│       │   └── websocket.py
│       ├── alembic/
│       │   └── versions/ (27 migration files)
│       └── api/
│           └── v1/                         ← Legacy API v1 Endpoints (35 files)
│               ├── __init__.py
│               ├── admin.py
│               ├── admin_analytics.py
│               ├── admin_billing.py
│               ├── admin_dlq.py
│               ├── admin_extractor.py
│               ├── admin_jobs.py
│               ├── admin_team.py
│               ├── admin_team_billing.py
│               ├── admin_webhook_dlq.py
│               ├── api_keys.py
│               ├── auth.py
│               ├── billing.py
│               ├── billing_dashboard.py
│               ├── bulk.py
│               ├── bulk_compat.py
│               ├── bulk_download.py
│               ├── checkout.py
│               ├── decision_makers.py
│               ├── extractor.py
│               ├── plans.py
│               ├── pricing.py
│               ├── subscription_events.py
│               ├── subscriptions.py
│               ├── subscriptions_db.py
│               ├── system.py
│               ├── team.py
│               ├── team_billing.py
│               ├── teams.py
│               ├── usage.py
│               ├── usage_user.py
│               ├── user_billing.py
│               ├── users.py
│               ├── verification.py
│               └── webhooks.py
├── Frontend/
│   ├── app/
│   │   └── admin/
│   └── lib/
│       └── axios.ts
├── Documentation/
├── README.md
└── SECURITY.md



The full, integrated directory tree for the Email-verification-saas/ project, including the detailed contents of the Backend/app/tasks/ directory, is below.
🌳 Project Directory Tree: Email-Verification-SaaS
Email-verification-saas/
├── .github/
│   └── workflows/
│       ├── codeql.yml
│       └── update-tree.yml
├── Backend/
│   ├── .env.prod
│   ├── .environment.dev
│   ├── docker-compose.yml
│   ├── requirements.txt
│   ├── billing/
│   │   ├── __init__.py
│   │   ├── plans.py
│   │   ├── razorpay_handlers.py
│   │   ├── stripe_handlers.py
│   │   └── upi_handlers.py
│   ├── scripts/
│   │   └── simulate_bulk_job.py
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_api_keys.py
│   │   ├── test_auth.py
│   │   ├── test_bulk_jobs.py
│   │   ├── test_credits.py
│   │   ├── test_decision_maker.py
│   │   ├── test_extractor.py
│   │   ├── test_plans.py
│   │   ├── test_subscription.py
│   │   ├── test_team_billing.py
│   │   ├── test_team_service.py
│   │   ├── test_usage_logs.
│   │   ├── test_user.py
│   │   ├── test_verification.py
│   │   ├── test_webhook_dlq.py
│   │   ├── test_webhook_endpoint.py
│   │   ├── test_webhook_events.py
│   │   └── utils.py
│   └── app/
│       ├── __init__.py
│       ├── celery_app.py
│       ├── config.py
│       ├── db.py
│       ├── main.py
│       ├── utils/
│       │   ├── __init__.py
│       │   ├── hashing.py
│       │   ├── helpers.py
│       │   └── security.py
│       ├── tasks/
│       │   ├── **bulk_tasks.py**
│       │   ├── **dlq_retry.py**
│       │   ├── **dlq_retry_task.py**
│       │   ├── **process_bulk.py**
│       │   ├── **scheduled.py**
│       │   └── **webhook_tasks.py**
│       ├── workers/
│       │   ├── __init__.py
│       │   ├── billing_tasks.py
│       │   ├── bulk_tasks.py
│       │   ├── decision_maker_tasks.py
│       │   ├── extractor_task_async.py
│       │   ├── extractor_tasks.py
│       │   ├── job_watcher.py
│       │   ├── scheduler.py
│       │   └── tasks.py
│       ├── models/
│       │   ├── __init__.py
│       │   ├── api_key.py
│       │   ├── api_usage_summary.py
│       │   ├── audit_log.py
│       │   ├── base.py
│       │   ├── bulk_job.py
│       │   ├── credit_reservation.py
│       │   ├── credit_transaction.py
│       │   ├── decision_maker.py
│       │   ├── domain_cache.py
│       │   ├── extractor_job.py
│       │   ├── failed_job.py
│       │   ├── plan.py
│       │   ├── subscription.py
│       │   ├── suppression.py
│       │   ├── team.py
│       │   ├── team_balance.py
│       │   ├── team_credit_transaction.py
│       │   ├── team_member.py
│       │   ├── usage_log.py
│       │   ├── user.py
│       │   ├── verification_result.py
│       │   ├── webhook_dlq.py
│       │   ├── webhook_endpoint.py
│       │   └── webhook_event.py
│       ├── schemas/
│       │   ├── __init__.py
│       │   ├── api_key.py
│       │   ├── api_usage_summary.py
│       │   ├── audit_log.py
│       │   ├── base.py
│       │   ├── bulk_job.py
│       │   ├── credit_reservation.py
│       │   ├── credit_transaction.py
│       │   ├── decision_maker.py
│       │   ├── domain_cache.py
│       │   ├── extractor_job.py
│       │   ├── failed_job.py
│       │   ├── plan.py
│       │   ├── subscription.py
│       │   ├── suppression.py
│       │   ├── team.py
│       │   ├── team_balance.py
│       │   ├── team_credit_transaction.py
│       │   ├── team_member.py
│       │   ├── usage_log.py
│       │   ├── user.py
│       │   ├── verification_result.py
│       │   ├── webhook_endpoint.py
│       │   └── webhook_event.py
│       ├── services/
│       │   ├── __init__.py
│       │   ├── acl_matrix.py
│       │   ├── analytics.py
│       │   ├── api_key_service.py
│       │   ├── apollo_client.py
│       │   ├── auth_service.py
│       │   ├── auto_topup.py
│       │   ├── billing_service.py
│       │   ├── bounce_classifier.py
│       │   ├── bulk_processor.py
│       │   ├── cache.py
│       │   ├── credits_service.py
│       │   ├── csv_parser.py
│       │   ├── decision_cache.py
│       │   ├── decision_maker_service.py
│       │   ├── decision_quota.py
│       │   ├── deliverability_monitor.py
│       │   ├── disposable_detector.py
│       │   ├── domain_backoff.py
│       │   ├── domain_throttle.py
│       │   ├── email_pattern_engine.py
│       │   ├── extractor_engine.py
│       │   ├── grok_client.py
│       │   ├── ip_intelligence.py
│       │   ├── minio_client.py
│       │   ├── minio_signed_url.py
│       │   ├── monitoring_service.py
│       │   ├── mx_lookup.py
│       │   ├── pattern_verifier.py
│       │   ├── pdl_client.py
│       │   ├── plan_service.py
│       │   ├── pricing_service.py
│       │   ├── processing_lock.py
│       │   ├── redis_rate_limiter.py
│       │   ├── reservation_finalizer.py
│       │   ├── smtp_probe.py
│       │   ├── spam_checker.py
│       │   ├── storage_s3.py
│       │   ├── stripe_handlers.py
│       │   ├── subscription_service.py
│       │   ├── team_billing_service.py
│       │   ├── team_check.py
│       │   ├── team_context.py
│       │   ├── team_service.py
│       │   ├── usage_service.py
│       │   ├── verification_engine.py
│       │   ├── verification_score.py
│       │   ├── webhook_dispatcher.py
│       │   ├── webhook_sender.py
│       │   └── webhook_service.py
│       ├── repositories/
│       │   ├── api_key_repository.py
│       │   ├── audit_log_repository.py
│       │   ├── base.py
│       │   ├── bulk_job_repository.py
│       │   ├── credit_reservation_repository.py
│       │   ├── credit_transaction_repository.py
│       │   ├── decision_maker_repository.py
│       │   ├── domain_cache_repository.py
│       │   ├── extractor_job_repository.py
│       │   ├── failed_job_repository.py
│       │   ├── plan_repository.py
│       │   ├── subscription_repository.py
│       │   ├── suppression_repository.py
│       │   ├── team_member_repository.py
│       │   ├── team_repository.py
│       │   ├── usage_log_repository.py
│       │   ├── user_repository.py
│       │   ├── verification_result_repository.py
│       │   ├── webhook_dlq_repository.py
│       │   ├── webhook_endpoint_repository.py
│       │   └── webhook_event_repository.py
│       ├── routers/
│       │   ├── __init__.py
│       │   ├── admin.py
│       │   ├── api_keys.py
│       │   ├── auth.py
│       │   ├── billing.py
│       │   ├── bulk_jobs.py
│       │   ├── decision_maker.py
│       │   ├── suppression.py
│       │   ├── team.py
│       │   ├── usage_logs.py
│       │   ├── users.py
│       │   ├── verification.py
│       │   ├── webhook_endpoint.py
│       │   └── webhook_event.py
│       ├── middleware/
│       │   ├── __init__.py
│       │   ├── api_key_guard.py
│       │   ├── audit_middleware.py
│       │   ├── cors.py
│       │   ├── rate_limiter.py
│       │   ├── request_logger.py
│       │   ├── team_acl.py
│       │   └── team_context.py
│       ├── admin_extra/
│       │   ├── __init__.py
│       │   ├── charts.py
│       │   ├── exports.py
│       │   └── websocket.py
│       ├── alembic/
│       │   ├── env.py
│       │   ├── script.py.mako
│       │   └── versions/
│       │       ├── 0001_initial.py
│       │       ├── 0002_add_plans_and_billing.py
│       │       ├── 0002_add_plans_and_user_plan.py
│       │       ├── 0002_add_plans_and_webhook_events.py
│       │       ├── 0002_create_teams_and_teamid_bulkjob.py
│       │       ├── 0003_add_teamid_bulkjob_and_credit_tx.py
│       │       ├── 0003_add_user_credits.py
│       │       ├── 0003_add_user_plan_column.py
│       │       ├── 0004_add_bulkjob_team_est_cost.py
│       │       ├── 0004_create_credit_reservations.py
│       │       ├── 0005_create_team_tables.py
│       │       ├── 0006_bulkjob_team_output.py
│       │       ├── 0007_create_usage_logs.py
│       │       ├── 20250222_01_team_billing.py
│       │       ├── 20251122_add_teams_and_billing.py
│       │       ├── 20251122_add_teams_and_team_reservations.py
│       │       ├── add_credits_to_users.py
│       │       ├── add_job_id_to_credit_reservations.py
│       │       ├── add_plan_to_users.py
│       │       ├── add_subscription_table.py
│       │       ├── add_team_id_to_bulk_jobs.py
│       │       ├── add_team_id_to_extractor_jobs.py
│       │       ├── cleanup_future-proof.py
│       │       ├── create_team_members_table.py
│       │       ├── create_teams_table.py
│       │       ├── performance_indexes.py
│       │       └── seed_plans.py
│       └── api/
│           └── v1/
│               ├── __init__.py
│               ├── admin.py
│               ├── admin_analytics.py
│               ├── admin_billing.py
│               ├── admin_dlq.py
│               ├── admin_extractor.py
│               ├── admin_jobs.py
│               ├── admin_team.py
│               ├── admin_team_billing.py
│               ├── admin_webhook_dlq.py
│               ├── api_keys.py
│               ├── auth.py
│               ├── billing.py
│               ├── billing_dashboard.py
│               ├── bulk.py
│               ├── bulk_compat.py
│               ├── bulk_download.py
│               ├── checkout.py
│               ├── decision_makers.py
│               ├── extractor.py
│               ├── plans.py
│               ├── pricing.py
│               ├── subscription_events.py
│               ├── subscriptions.py
│               ├── subscriptions_db.py
│               ├── system.py
│               ├── team.py
│               ├── team_billing.py
│               ├── teams.py
│               ├── usage.py
│               ├── usage_user.py
│               ├── user_billing.py
│               ├── users.py
│               ├── verification.py
│               └── webhooks.py
├── Frontend/
│   ├── app/
│   │   └── admin/
│   └── lib/
│       └── axios.ts
├── Documentation/
├── README.md
├── SECURITY.md
└── docker-compose.prod.yml


