from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class Location(BaseModel):
    """Location information for a job posting"""
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    countryCode: Optional[str] = Field(None, alias="countryCode")
    remote: Optional[bool] = None


class Company(BaseModel):
    """Company information"""
    identifier: Optional[str] = None
    name: Optional[str] = None


class Department(BaseModel):
    """Department information"""
    label: Optional[str] = None


class TypeOfEmployment(BaseModel):
    """Employment type information"""
    label: Optional[str] = None


class ExperienceLevel(BaseModel):
    """Experience level information"""
    label: Optional[str] = None


class SmartRecruitersPosting(BaseModel):
    """Represents a single job posting from SmartRecruiters API"""
    id: Optional[str] = None
    name: Optional[str] = None  # Job title
    location: Optional[Location] = None
    company: Optional[Company] = None
    department: Optional[Department] = None
    typeOfEmployment: Optional[TypeOfEmployment] = Field(None, alias="typeOfEmployment")
    experienceLevel: Optional[ExperienceLevel] = Field(None, alias="experienceLevel")
    releasedDate: Optional[str] = Field(None, alias="releasedDate")
    refNumber: Optional[str] = Field(None, alias="refNumber")
    applyUrl: Optional[str] = Field(None, alias="applyUrl")
    jobAd: Optional[Dict[str, Any]] = Field(None, alias="jobAd")
    # Additional fields that might be present
    uuid: Optional[str] = None
    customField: Optional[List[Dict[str, Any]]] = Field(None, alias="customField")

    @property
    def job_url(self) -> Optional[str]:
        """Generate job URL from posting data"""
        if not self.company or not self.company.identifier:
            return None
        if not self.id:
            return None
        
        # Construct URL: https://jobs.smartrecruiters.com/{companyIdentifier}/{id-slug}
        # If name exists, create slug from it, otherwise use ID
        slug = ""
        if self.name:
            # Create a slug from the job name
            slug = self.name.lower().replace(" ", "-").replace(",", "").replace("/", "-")
            slug = "".join(c for c in slug if c.isalnum() or c == "-")
            slug = "-".join(filter(None, slug.split("-")))
        
        if slug:
            return f"https://jobs.smartrecruiters.com/{self.company.identifier}/{self.id}-{slug}"
        return f"https://jobs.smartrecruiters.com/{self.company.identifier}/{self.id}"


class SmartRecruitersApiResponse(BaseModel):
    """Response wrapper for SmartRecruiters API"""
    content: List[SmartRecruitersPosting] = []
    totalFound: Optional[int] = Field(None, alias="totalFound")
    limit: Optional[int] = None
    offset: Optional[int] = None
    last_scraped: Optional[str] = None
    name: Optional[str] = None  # Company name stored by scraper
