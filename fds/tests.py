from django.test import TestCase

# Re-export all comprehensive 4-Tier test cases and 24 edge cases for Django DiscoverRunner
from .test_fds_fee_system import (
    FdsFeeSystemTier1FeatureTests,
    FdsFeeSystemTier2BoundaryTests,
    FdsFeeSystemTier3CrossFeatureTests,
    FdsFeeSystemTier4RealWorldWorkloadTests,
    PaymentStatusEdgeCaseTests,
    AccountLinkingEdgeCaseTests,
    RecurringCycleEdgeCaseTests,
    ReceiptGenerationEdgeCaseTests,
)

__all__ = [
    'FdsFeeSystemTier1FeatureTests',
    'FdsFeeSystemTier2BoundaryTests',
    'FdsFeeSystemTier3CrossFeatureTests',
    'FdsFeeSystemTier4RealWorldWorkloadTests',
    'PaymentStatusEdgeCaseTests',
    'AccountLinkingEdgeCaseTests',
    'RecurringCycleEdgeCaseTests',
    'ReceiptGenerationEdgeCaseTests',
]
