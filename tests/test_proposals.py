import copy

import pytest

from resume_tailor.proposals import ProposalError, validate_proposal


RESUME = 'Avery Example\navery@example.com\nEngineer at ExampleCo, 2020 to 2024\nBuilt reliable Java services.'
JOB = 'Backend engineer needed to build Java services. Python is a preferred skill.'


def proposal():
    return {
        'sections': [
            {'heading': 'Contact', 'lines': [{'text': 'Avery Example', 'evidence': ['Avery Example']},
                                            {'text': 'avery@example.com', 'evidence': ['avery@example.com']}]},
            {'heading': 'Experience', 'lines': [{'text': 'Engineer at ExampleCo, 2020 to 2024', 'evidence': ['Engineer at ExampleCo, 2020 to 2024']},
                                               {'text': 'Built dependable Java services.', 'evidence': ['Built reliable Java services.']}]},
        ],
        'changes': [{'before': 'Built reliable Java services.', 'after': 'Built dependable Java services.',
                     'reason': 'Clarifies relevant backend work.'}],
        'alignment': [{'point':'Java service experience relates to the backend role.',
                       'resume_evidence':'Built reliable Java services.', 'job_evidence':'build Java services'}],
        'suggestions': [{'skill': 'Python', 'job_evidence': 'Python is a preferred skill.'}],
    }


def test_accepts_traceable_changes_and_keeps_suggestions_separate():
    result = validate_proposal(proposal(), RESUME, JOB)
    assert 'dependable Java services' in result.resume_text()
    assert 'Python' not in result.resume_text()
    assert result.suggestions[0].skill == 'Python'


@pytest.mark.parametrize('suggestion', [
    {'skill': 'Docker', 'job_evidence': 'Docker experience preferred.'},
    {'skill': 'Python', 'job_evidence': 'Python is preferred.'},
    {'skill': 'Python programming', 'job_evidence': 'Python is a preferred skill.'},
    {'skill': 'Python', 'job_evidence': 'Python is a preferred skill!'},
])
def test_unsupported_suggestion_does_not_block_a_grounded_resume(suggestion):
    data = proposal()
    data['suggestions'].append(suggestion)
    result = validate_proposal(data, RESUME, JOB)
    assert 'dependable Java services' in result.resume_text()
    assert [item.skill for item in result.suggestions] == ['Python']
    assert result.warnings


@pytest.mark.parametrize('mutation', ['missing_source', 'invented_number', 'unconfirmed_skill', 'missing_contact'])
def test_rejects_unsupported_output(mutation):
    data = copy.deepcopy(proposal())
    if mutation == 'missing_source':
        data['sections'][1]['lines'][1]['evidence'] = ['Unrelated invented source']
    elif mutation == 'invented_number':
        data['sections'][1]['lines'][1]['text'] = 'Led 99 engineers.'
        data['changes'] = []
    elif mutation == 'unconfirmed_skill':
        data['sections'][1]['lines'][1]['text'] = 'Built Python services.'
        data['changes'] = []
    else:
        data['sections'][0]['lines'] = data['sections'][0]['lines'][:1]
    with pytest.raises(ProposalError):
        validate_proposal(data, RESUME, JOB)


@pytest.mark.parametrize('kind', ['change', 'alignment'])
def test_unverified_explanations_are_omitted_without_losing_the_resume(kind):
    data = proposal()
    if kind == 'change':
        data['changes'][0]['before'] = 'Not found in the resume.'
    else:
        data['alignment'][0]['job_evidence'] = 'Not found in the job.'
    result = validate_proposal(data, RESUME, JOB)
    assert 'dependable Java services' in result.resume_text()
    assert not (result.changes if kind == 'change' else result.alignment)
    assert result.warnings


def test_unconfirmed_skill_is_rejected_even_if_its_suggestion_is_unverified():
    data = proposal()
    data['sections'][1]['lines'][1]['text'] = 'Built Python services.'
    data['changes'] = []
    data['suggestions'][0]['job_evidence'] = 'This quote is not in the job description.'
    with pytest.raises(ProposalError, match='not been confirmed'):
        validate_proposal(data, RESUME, JOB)


def test_unknown_sections_or_extra_fields_are_rejected():
    data = proposal()
    data['sections'][1]['heading'] = 'Invented Company'
    with pytest.raises(ProposalError):
        validate_proposal(data, RESUME, JOB)
