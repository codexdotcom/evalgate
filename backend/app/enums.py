from enum import Enum


class Verdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NEEDS_REVIEW = "needs_review"


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    RESOLVED = "resolved"