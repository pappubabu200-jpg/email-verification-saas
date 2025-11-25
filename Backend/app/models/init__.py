# backend/app/models/__init__.py

from .base import Base

# -----------------------------------
# User & Authentication
# -----------------------------------
from .user import User
from .api_key import ApiKey

# -----------------------------------
# Billing / Plans / Subscription
# -----------------------------------
from .plan import Plan
from .subscription import Subscription
from .credit_transaction import CreditTransaction
from .credit_reservation import CreditReservation

# -----------------------------------
# Teams
# -----------------------------------
from .team import Team
from .team_member import TeamMember
from .team_balance import TeamBalance
from .team_credit_transaction import TeamCreditTransaction

# -----------------------------------
# Verification Engine
# -----------------------------------
from .verification_result import VerificationResult
from .bulk_job import BulkJob
from .extractor_job import ExtractorJob
from .suppression import Suppression
from .decision_maker import DecisionMaker

# -----------------------------------
# Webhooks
# -----------------------------------
from .webhook_endpoint import WebhookEndpoint
from .webhook_event import WebhookEvent
from .webhook_dlq import WebhookDLQ

# -----------------------------------
# Logs & Analytics
# -----------------------------------
from .usage_log import UsageLog
from .audit_log import AuditLog
from .api_usage_summary import ApiUsageSummary

# -----------------------------------
# Enterprise Add-Ons
# -----------------------------------
from .domain_cache import DomainCache
from .failed_job import FailedJob

