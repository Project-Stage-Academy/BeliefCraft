from sqlalchemy import CheckConstraint


def check_non_negative(column: str, name: str | None = None) -> CheckConstraint:
    return CheckConstraint(f"{column} >= 0", name=name)


def check_positive(column: str, name: str | None = None) -> CheckConstraint:
    return CheckConstraint(f"{column} > 0", name=name)


def check_between_zero_one(column: str, name: str | None = None) -> CheckConstraint:
    return CheckConstraint(f"{column} >= 0 AND {column} <= 1", name=name)
