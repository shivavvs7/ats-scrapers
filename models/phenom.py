"""
Pydantic model for Phenom People ATS jobs.

Phenom is used by companies like Bell Canada, GE Healthcare, and many others.
Each company has custom branded domains (e.g., jobs.bell.ca, careers.gehealthcare.com).
"""

from pydantic import BaseModel
from typing import List, Optional


class PhenomJob(BaseModel):
    """
    Phenom People job model based on API response.

    Phenom job data structure varies slightly by company configuration,
    but these are the common fields returned by the /widgets API endpoint.
    """

    # Identifiers
    jobId: Optional[str] = None
    reqId: Optional[str] = None

    # Job Details
    title: Optional[str] = None
    description: Optional[str] = None

    # Location
    location: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    multi_location: Optional[List[str]] = None

    # Categorization
    category: Optional[str] = None
    subCategory: Optional[str] = None
    experienceLevel: Optional[str] = None

    # Metadata
    postedDate: Optional[str] = None
    ml_skills: Optional[List[str]] = None

    # Employment Details
    employmentType: Optional[str] = None
    workType: Optional[str] = None

    # Additional fields that may be present
    jobCategory: Optional[str] = None
    jobFamilies: Optional[List[str]] = None

    class Config:
        # Allow extra fields that may vary by company
        extra = "allow"
