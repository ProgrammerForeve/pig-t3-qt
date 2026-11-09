from dataclasses import dataclass, field
from typing import List

@dataclass
class Issue:
    tool: str
    msg: str
    line: int
    severity: str = "info"  # info, warning, error

@dataclass
class FileMetrics:
    path: str
    sloc: int = 0
    complexity: float = 1.0  # Default 1.0 (lowest complexity)
    maintainability: float = 0.0  # Default 0.0 (Worst case to indicate scan failure/issue)
    pylint_score: float = 10.0  # Starts perfect, penalties apply
    security_issues: int = 0
    issues: List[Issue] = field(default_factory=list)
    
    @property
    def status_cc(self) -> str:
        # Radon CC: A(1-5), B(6-10), C(11-20), D(21-30), E(31-40), F(41+)
        # Simplified: Green <= 10, Yellow <= 20, Red > 20
        if self.complexity <= 10:
            return "green"
        if self.complexity <= 20:
            return "yellow"
        return "red"

    @property
    def status_mi(self) -> str:
        # Radon MI: 100-20 (A/B/C) is generally acceptable.
        # < 20 is Bad. 
        # We set boundaries: > 20 is Green, > 10 Yellow, <= 10 Red.
        if self.maintainability >= 20:
            return "green"
        if self.maintainability >= 10:
            return "yellow"
        return "red"

    @property
    def status_pylint(self) -> str:
        # Pylint: > 8 Green, > 5 Yellow, <= 5 Red
        if self.pylint_score >= 8.0:
            return "green"
        if self.pylint_score >= 5.0:
            return "yellow"
        return "red"

    @property
    def status_security(self) -> str:
        # Any High/Medium issue is Red.
        if self.security_issues == 0:
            return "green"
        if self.security_issues < 2:
            return "yellow"
        return "red"
    def get_status_for_column(self, col: str) -> str:
        # Returns status color based on the specific column key
        if col == "sloc": return "green"  # Always green/neutral for lines count
        if col == "cc": return self.status_cc
        if col == "mi": return self.status_mi
        if col == "score": return self.status_pylint
        if col == "sec": return self.status_security
        return self.overall_status

    @property
    def overall_status(self) -> str:
        statuses = [self.status_cc, self.status_mi, self.status_pylint, self.status_security]
        if "red" in statuses:
            return "red"
        if "yellow" in statuses:
            return "yellow"
        return "green"
