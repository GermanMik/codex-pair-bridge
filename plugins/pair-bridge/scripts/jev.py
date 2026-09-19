"""Optional, explicit TypeSafe AI Jev decision adapter. Never used for local chat."""
import os
import httpx


def decide(state: str, instructions: str, criteria: dict[str, str], *, allow_external: bool,
           model: str = 'jev-latest') -> dict:
    if not allow_external:
        raise ValueError('Jev sends state to TypeSafe AI; set allow_external=true explicitly')
    key = os.environ.get('TYPESAFE_API_KEY')
    if not key:
        raise ValueError('TYPESAFE_API_KEY is not configured')
    if not state.strip() or len(state) > 48000 or not instructions.strip() or len(instructions) > 1000:
        raise ValueError('State or instructions are empty or too long')
    if not 2 <= len(criteria) <= 32 or any(not isinstance(k, str) or not k or len(k) > 64 or
                                           not isinstance(v, str) or not v or len(v) > 500
                                           for k, v in criteria.items()):
        raise ValueError('Choice requires 2-32 named options with short descriptions')
    payload = {'model': model, 'state': state,
               'questions': {'decision': {'type': 'choice', 'instructions': instructions,
                                          'criteria': criteria}}}
    try:
        with httpx.Client(timeout=30, trust_env=False, follow_redirects=False) as client:
            response = client.post('https://api.typesafe.ai/v1/systemone',
                                   headers={'Authorization': 'Bearer ' + key}, json=payload)
    except httpx.RequestError as exc:
        raise ValueError('Jev is unreachable; no automatic retry or fallback was made') from exc
    if not response.is_success:
        raise ValueError(f'Jev returned HTTP {response.status_code}; no automatic retry was made')
    try:
        result = response.json()
    except ValueError as exc:
        raise ValueError('Jev returned non-JSON data') from exc
    answer = result.get('answers', {}).get('decision') if isinstance(result, dict) else None
    if not isinstance(answer, dict) or answer.get('type') != 'choice' or answer.get('choice') not in criteria:
        raise ValueError('Jev returned an invalid choice')
    probabilities = answer.get('probabilities')
    confidence = answer.get('confidence')
    if not isinstance(probabilities, dict) or set(probabilities) != set(criteria) or any(
        not isinstance(p, (int, float)) or isinstance(p, bool) or not 0 <= p <= 1
        for p in probabilities.values()
    ) or abs(sum(probabilities.values()) - 1) > .02 or not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
        raise ValueError('Jev returned invalid probabilities or confidence')
    return {'model': result.get('model'), 'choice': answer['choice'],
            'probabilities': probabilities, 'confidence': confidence,
            'usage': result.get('usage'), 'external_service': 'TypeSafe AI'}


def score(state: str, instructions: str, levels: list[str], *, allow_external: bool,
          model: str = 'jev-latest') -> dict:
    """Evaluate an ordered rubric with Jev; this never runs as a chat completion."""
    if not allow_external:
        raise ValueError('Jev sends state to TypeSafe AI; set allow_external=true explicitly')
    key = os.environ.get('TYPESAFE_API_KEY')
    if not key:
        raise ValueError('TYPESAFE_API_KEY is not configured')
    if not state.strip() or len(state) > 48000 or not instructions.strip() or len(instructions) > 1000:
        raise ValueError('State or instructions are empty or too long')
    if not 2 <= len(levels) <= 32 or any(not isinstance(v, str) or not v or len(v) > 500 for v in levels):
        raise ValueError('Score requires 2-32 ordered short level descriptions')
    payload = {'model': model, 'state': state,
               'questions': {'decision': {'type': 'score', 'instructions': instructions,
                                          'criteria': levels}}}
    try:
        with httpx.Client(timeout=30, trust_env=False, follow_redirects=False) as client:
            response = client.post('https://api.typesafe.ai/v1/systemone',
                                   headers={'Authorization': 'Bearer ' + key}, json=payload)
    except httpx.RequestError as exc:
        raise ValueError('Jev is unreachable; no automatic retry or fallback was made') from exc
    if not response.is_success:
        raise ValueError(f'Jev returned HTTP {response.status_code}; no automatic retry was made')
    try:
        result = response.json()
    except ValueError as exc:
        raise ValueError('Jev returned non-JSON data') from exc
    answer = result.get('answers', {}).get('decision') if isinstance(result, dict) else None
    expected = {str(i): level for i, level in enumerate(levels)}
    if not isinstance(answer, dict) or answer.get('type') != 'score' or answer.get('legend') != expected:
        raise ValueError('Jev returned an invalid score legend')
    probabilities = answer.get('probabilities')
    value = answer.get('score')
    confidence = answer.get('confidence')
    numeric = lambda n: isinstance(n, (int, float)) and not isinstance(n, bool)
    if not isinstance(probabilities, dict) or set(probabilities) != set(expected) or any(
        not numeric(p) or not 0 <= p <= 1 for p in probabilities.values()
    ) or abs(sum(probabilities.values()) - 1) > .02 or not numeric(value) or not 0 <= value <= len(levels)-1 or not numeric(confidence) or not 0 <= confidence <= 1:
        raise ValueError('Jev returned invalid score probabilities or confidence')
    return {'model': result.get('model'), 'score': value, 'legend': expected,
            'probabilities': probabilities, 'confidence': confidence,
            'usage': result.get('usage'), 'external_service': 'TypeSafe AI'}
