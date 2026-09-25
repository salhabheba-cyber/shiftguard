"""Send a CV to Claude and get back structured candidate data + a rating."""
from typing import List, Literal, Optional

import anthropic
from pydantic import BaseModel

from config import ANTHROPIC_API_KEY, CLAUDE_EFFORT, CLAUDE_MODEL


class Education(BaseModel):
    degree: str
    institution: str
    year: str


class Experience(BaseModel):
    title: str
    company: str
    period: str
    summary: str


class CriterionScore(BaseModel):
    criterion: str
    score: int          # 0-10
    comment: str


class CVAnalysis(BaseModel):
    full_name: str
    email: str
    phone: str
    location: str
    linkedin: str
    current_title: str
    total_years_experience: Optional[float]
    education: List[Education]
    experience: List[Experience]
    skills: List[str]
    languages: List[str]
    certifications: List[str]
    summary: str
    criteria_scores: List[CriterionScore]
    strengths: List[str]
    gaps: List[str]
    score: int          # 0-100
    recommendation: Literal['Strong fit', 'Good fit', 'Possible fit', 'Not a fit']


SYSTEM_TEMPLATE = """You are an experienced recruiter screening CVs for one specific job.

For each CV you receive:
1. Extract the candidate's details exactly as written. Use an empty string when a field
   is missing (never invent contact details). total_years_experience is your best
   estimate of relevant professional experience in years, or null if it cannot be judged.
2. Write a short, neutral summary (3-5 sentences) of who the candidate is and what they bring.
3. Rate the candidate against the job below. Break the hiring manager's rating criteria
   into individual criteria and give each a 0-10 score with a one-line justification.
   If no criteria are given, derive them from the job description.
4. Give an overall score from 0 to 100 reflecting fit for THIS job (not general quality),
   list concrete strengths and gaps, and a recommendation:
   80-100 "Strong fit", 65-79 "Good fit", 45-64 "Possible fit", below 45 "Not a fit".

Judge only on job-relevant qualifications and evidence in the CV. Ignore age, gender,
ethnicity, religion, marital status, photos and other protected characteristics.
Write the summary, strengths and gaps in the same language as the job description.

<job>
<title>{title}</title>
<description>
{description}
</description>
<rating_criteria>
{criteria}
</rating_criteria>
</job>"""


class AnalysisError(Exception):
    pass


_client = None


def client():
    global _client
    if _client is None:
        if not ANTHROPIC_API_KEY:
            raise AnalysisError('ANTHROPIC_API_KEY is not set on the server.')
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, max_retries=4)
    return _client


def analyze(job, content_blocks):
    system = SYSTEM_TEMPLATE.format(
        title=job['title'],
        description=job['description'] or '(none given)',
        criteria=job['criteria'] or '(none given — derive criteria from the description)',
    )
    try:
        response = client().beta.messages.parse(
            model=CLAUDE_MODEL,
            max_tokens=16000,
            # The job prompt is identical for every CV in a job, so cache it.
            system=[{'type': 'text', 'text': system, 'cache_control': {'type': 'ephemeral'}}],
            messages=[{
                'role': 'user',
                'content': content_blocks + [{'type': 'text', 'text': 'Analyse this CV for the job.'}],
            }],
            thinking={'type': 'adaptive'},
            output_config={'effort': CLAUDE_EFFORT},
            output_format=CVAnalysis,
            # If the model declines, retry automatically on Anthropic's recommended fallback.
            betas=['server-side-fallback-2026-07-01'],
            fallbacks='default',
        )
    except anthropic.AuthenticationError:
        raise AnalysisError('Invalid ANTHROPIC_API_KEY.')
    except anthropic.BadRequestError as e:
        raise AnalysisError(f'Claude rejected the request: {e.message}')
    except anthropic.RateLimitError:
        raise AnalysisError('Rate limited by Claude API — use "Retry failed" in a minute.')
    except anthropic.APIStatusError as e:
        raise AnalysisError(f'Claude API error ({e.status_code}): {e.message}')
    except anthropic.APIConnectionError:
        raise AnalysisError('Could not reach the Claude API.')

    if response.stop_reason == 'refusal':
        raise AnalysisError('Claude declined to analyse this file.')
    if response.stop_reason == 'max_tokens':
        raise AnalysisError('The response was cut off (CV too long?).')
    if response.parsed_output is None:
        raise AnalysisError('Claude did not return a valid analysis.')

    data = response.parsed_output.model_dump()
    data['score'] = max(0, min(100, int(data['score'])))
    for c in data['criteria_scores']:
        c['score'] = max(0, min(10, int(c['score'])))
    return data
