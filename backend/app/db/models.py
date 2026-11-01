import uuid
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
)
from sqlalchemy.orm import relationship
from backend.app.db.session import Base


def generate_uuid() -> str:
    """Generate a UUID4 string identifier."""
    return str(uuid.uuid4())


class Project(Base):
    """Represents an ingested target codebase for test analysis."""

    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False, index=True)
    source_archive_path = Column(String(1024), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    test_cases = relationship("TestCase", back_populates="project", cascade="all, delete-orphan")
    test_runs = relationship("TestRun", back_populates="project", cascade="all, delete-orphan")


class TestCase(Base):
    """Represents an individual pytest test function or method discovered in a project."""

    __tablename__ = "test_cases"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    file_path = Column(String(1024), nullable=False)
    test_name = Column(String(255), nullable=False)
    node_id = Column(String(1024), nullable=False, index=True)
    discovered_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    project = relationship("Project", back_populates="test_cases")
    test_iterations = relationship("TestIteration", back_populates="test_case", cascade="all, delete-orphan")
    flakiness_reports = relationship("FlakinessReport", back_populates="test_case", cascade="all, delete-orphan")


class TestRun(Base):
    """Represents an overarching diagnostic execution session running tests N times."""

    __tablename__ = "test_runs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    iteration_count = Column(Integer, nullable=False, default=10)
    shuffle_order = Column(Boolean, nullable=False, default=True)
    status = Column(String(50), nullable=False, default="PENDING")  # PENDING, RUNNING, COMPLETED, FAILED
    total_tests = Column(Integer, default=0, nullable=False)
    consistently_passing_count = Column(Integer, default=0, nullable=False)
    consistently_failing_count = Column(Integer, default=0, nullable=False)
    flaky_tests_count = Column(Integer, default=0, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    project = relationship("Project", back_populates="test_runs")
    test_iterations = relationship("TestIteration", back_populates="test_run", cascade="all, delete-orphan")
    flakiness_reports = relationship("FlakinessReport", back_populates="test_run", cascade="all, delete-orphan")


class TestIteration(Base):
    """Stores execution evidence for a single test case run within a specific iteration."""

    __tablename__ = "test_iterations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    test_run_id = Column(String(36), ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    test_case_id = Column(String(36), ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    iteration_number = Column(Integer, nullable=False)
    status = Column(String(50), nullable=False)  # PASSED, FAILED, ERROR, SKIPPED
    duration_ms = Column(Float, default=0.0, nullable=False)
    execution_order = Column(Integer, default=0, nullable=False)
    random_order_seed = Column(Integer, nullable=True)
    stdout = Column(Text, nullable=True)
    stderr = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    traceback = Column(Text, nullable=True)

    # Relationships
    test_run = relationship("TestRun", back_populates="test_iterations")
    test_case = relationship("TestCase", back_populates="test_iterations")


class FlakinessReport(Base):
    """Synthesized flakiness diagnosis, classification, and heuristic RCA outcome."""

    __tablename__ = "flakiness_reports"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    test_run_id = Column(String(36), ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    test_case_id = Column(String(36), ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    outcome_classification = Column(String(50), nullable=False)  # CONSISTENTLY_PASSING, CONSISTENTLY_FAILING, FLAKY
    flakiness_score = Column(Float, default=0.0, nullable=False)
    total_runs = Column(Integer, default=0, nullable=False)
    pass_count = Column(Integer, default=0, nullable=False)
    fail_count = Column(Integer, default=0, nullable=False)
    flip_count = Column(Integer, default=0, nullable=False)
    root_cause_category = Column(String(100), nullable=True)
    confidence_score = Column(Float, default=0.0, nullable=False)
    rca_summary = Column(Text, nullable=True)
    recommendations = Column(Text, nullable=True)

    # Relationships
    test_run = relationship("TestRun", back_populates="flakiness_reports")
    test_case = relationship("TestCase", back_populates="flakiness_reports")

