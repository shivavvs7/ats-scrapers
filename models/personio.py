from pydantic import BaseModel, Field
from typing import List, Optional


class JobDescription(BaseModel):
    """Represents a job description section."""
    name: str
    value: str


class PersonioJob(BaseModel):
    """Represents a job posting from Personio."""
    id: str
    name: str
    slug: Optional[str] = None
    office: str
    all_offices: List[str] = Field(default_factory=list, alias="allOffices")
    employment_type: str = Field(alias="employmentType")
    department: str
    recruiting_category: Optional[str] = Field(None, alias="recruitingCategory")
    subcompany: Optional[str] = None
    seniority: Optional[str] = None
    schedule: Optional[str] = None
    compensation: Optional[str] = None
    created_at: Optional[str] = Field(None, alias="createdAt")
    other_offices: Optional[List[str]] = Field(None, alias="otherOffices")
    job_descriptions: Optional[List[JobDescription]] = Field(
        None, alias="jobDescriptions"
    )

    class Config:
        populate_by_name = True


class PersonioOffice(BaseModel):
    """Represents an office/location."""
    name: str


class PersonioDepartment(BaseModel):
    """Represents a department."""
    name: str


class PersonioApiResponse(BaseModel):
    """Response from Personio JSON API."""
    jobs: List[PersonioJob]

    @classmethod
    def from_json_list(cls, data: list):
        """Create response from JSON array of jobs."""
        return cls(jobs=[PersonioJob(**job) for job in data])
