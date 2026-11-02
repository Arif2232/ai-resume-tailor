"""Validate AI proposals and keep unconfirmed suggestions separate."""

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, PrivateAttr, ValidationError


class ProposalError(ValueError):
    pass


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class ResumeLine(StrictModel):
    text: str
    evidence: list[str]


class ResumeSection(StrictModel):
    heading: Literal['Contact', 'Summary', 'Skills', 'Experience', 'Projects', 'Education',
                     'Certifications', 'Awards', 'Languages', 'Volunteer', 'Publications', 'Other']
    lines: list[ResumeLine]


class Change(StrictModel):
    before: str
    after: str
    reason: str


class Suggestion(StrictModel):
    skill: str
    job_evidence: str


class Alignment(StrictModel):
    point: str
    resume_evidence: str
    job_evidence: str


class Proposal(StrictModel):
    sections: list[ResumeSection]
    changes: list[Change]
    alignment: list[Alignment]
    suggestions: list[Suggestion]
    _warnings: list[str] = PrivateAttr(default_factory=list)

    @property
    def warnings(self) -> list[str]:
        return list(self._warnings)

    def resume_text(self) -> str:
        parts = []
        for section in self.sections:
            lines = [line.text.strip() for line in section.lines]
            if section.heading != 'Contact':
                lines.insert(0, section.heading.upper())
            parts.append('\n'.join(lines))
        return '\n\n'.join(parts)


def normalize(value: str) -> str:
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())


def contains_phrase(phrase: str, text: str) -> bool:
    return bool(re.search(r'(?<!\w)' + re.escape(normalize(phrase)) + r'(?!\w)', normalize(text)))


def validate_proposal(data, resume: str, job: str) -> Proposal:
    try:
        result = Proposal.model_validate(data)
    except ValidationError as exc:
        raise ProposalError('The AI response was not in the expected format. Please try again.') from exc
    if not 1 <= len(result.sections) <= 25 or len(result.changes) > 60 or len(result.alignment) > 30 or len(result.suggestions) > 30:
        raise ProposalError('The AI response was too large or incomplete. Please try again.')
    source = normalize(resume)
    job_source = normalize(job)
    for section in result.sections:
        if not 1 <= len(section.lines) <= 80:
            raise ProposalError('The AI returned an incomplete resume. Please try again.')
        for line in section.lines:
            if not 1 <= len(line.text.strip()) <= 1000 or not 1 <= len(line.evidence) <= 5:
                raise ProposalError('The AI returned a claim without enough source evidence. Please try again.')
            if any(not 4 <= len(quote.strip()) <= 500 or normalize(quote) not in source for quote in line.evidence):
                raise ProposalError('The AI returned a claim without matching source evidence. Please try again.')
    text = result.resume_text()
    if len(text) > 50_000:
        raise ProposalError('The AI returned a resume that is too long. Please try again.')
    source_numbers = set(re.findall(r'(?<!\w)\d+(?:[.,]\d+)*', resume))
    if not set(re.findall(r'(?<!\w)\d+(?:[.,]\d+)*', text)).issubset(source_numbers):
        raise ProposalError('The AI added a number not found in the original resume. Please try again.')
    emails = {email.casefold() for email in re.findall(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', resume)}
    output_emails = {email.casefold() for email in re.findall(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', text)}
    if output_emails - emails or emails and not output_emails.intersection(emails):
        raise ProposalError('The AI changed or omitted an email address. Please try again.')
    original_counts = (len(result.changes), len(result.suggestions), len(result.alignment))
    result.changes = [change for change in result.changes
                      if 1 <= len(change.before.strip()) <= 500 and normalize(change.before) in source
                      and 1 <= len(change.after.strip()) <= 1000 and normalize(change.after) in normalize(text)
                      and 1 <= len(change.reason.strip()) <= 500]
    suggestions = []
    for suggestion in result.suggestions:
        skill = suggestion.skill.strip()
        if 1 <= len(skill) <= 120 and not any(ord(char) < 32 for char in skill) and contains_phrase(skill, text) and not contains_phrase(skill, resume):
            raise ProposalError('The AI added a suggested skill that has not been confirmed. Please try again.')
        if (1 <= len(skill) <= 120 and not any(ord(char) < 32 for char in skill)
                and 4 <= len(suggestion.job_evidence.strip()) <= 500
                and normalize(suggestion.job_evidence) in job_source and contains_phrase(skill, job)):
            suggestions.append(suggestion)
    result.suggestions = suggestions
    result.alignment = [item for item in result.alignment
                        if 1 <= len(item.point.strip()) <= 500 and 4 <= len(item.resume_evidence.strip()) <= 500
                        and 4 <= len(item.job_evidence.strip()) <= 500
                        and normalize(item.resume_evidence) in source and normalize(item.job_evidence) in job_source]
    if original_counts != (len(result.changes), len(result.suggestions), len(result.alignment)):
        result._warnings.append('Some suggestions or explanations could not be matched to the source text and were omitted.')
    return result
